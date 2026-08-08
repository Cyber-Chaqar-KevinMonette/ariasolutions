"""
provenance_tool.py — Tier 0: walk the causal chain of any artifact

provenance.walk_backward() already exists in the CLI ('sov provenance <node>').
This wraps it as an agent tool so Aria can trace the lineage of any node
from inside the loop — understanding where any atom, fact, recall, or
event came from.

Given any node_id (ULID or other ID), it walks backward through:
  - atoms: parent_atom_id (supersedes chain), parents JSON array
  - people_facts: source_event_id, atom_id
  - recalls: recall_sources, supersedes, atom companion
  - tasks, episodes, and any registered custom extractors

Returns: tree rendering, timeline, or raw JSON.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class TraceProvenanceTool(Tool):
    """Walk backward from any node through everything that informed it.

    Given a node_id (atom, fact, recall, event, task), traces the full
    upstream graph through every pointer in atoms.db: supersedes chains,
    source events, recall sources, parent atoms, and more.

    Use when:
      • You want to know where an atom came from
      • Debugging why a conclusion was reached
      • Understanding the evidence chain behind a remembered fact
      • Forensics after something unexpected happened

    Format options:
      tree     — indented tree with edge labels (default)
      json     — raw graph dict {nodes, edges, truncated}
      summary  — node count, depth, and edge type histogram

    Args:
      node_id  — any ULID or ID in atoms.db
      depth    — max walk depth (default 5, max 15)
      format   — tree | json | summary

    FAILURE MODES: node_not_found, db_unavailable, db_error.
    """

    name = "trace_provenance"
    tier = 0
    description = (
        "Walk backward from any node through everything that informed it. "
        "Args: node_id (str — any ULID/atom_id/fact_id), depth (int 1-15, default 5), "
        "format (tree | json | summary, default tree). "
        "FAILURE MODES: node_not_found, db_unavailable, db_error."
    )
    failure_modes = ("node_not_found", "db_unavailable", "db_error")

    class Args(BaseModel):
        node_id: str = Field(description="Node to trace (atom_id, fact_id, recall_id, event_id, etc).")
        depth: int = Field(default=5, ge=1, le=15, description="Max walk depth.")
        format: str = Field(default="tree", description="Output format: tree | json | summary.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        if not args.node_id.strip():
            return ToolResult(ok=False, error="node_id must not be empty")

        fmt = args.format.lower()
        if fmt not in ("tree", "json", "summary"):
            return ToolResult(ok=False, error=f"format must be tree, json, or summary; got {args.format!r}")

        try:
            from sovereign_agent.db import open_atoms_db
        except ImportError:
            return ToolResult(ok=False, error="db module not available")

        try:
            conn = open_atoms_db()
        except Exception as exc:
            return ToolResult(ok=False, error=f"db unavailable: {exc!r}")

        try:
            from sovereign_agent.provenance import walk_backward
            graph = walk_backward(
                conn,
                args.node_id.strip(),
                max_depth=args.depth,
                max_nodes=200,
            )
        except Exception as exc:
            conn.close()
            return ToolResult(ok=False, error=f"provenance walk failed: {exc!r}")
        finally:
            conn.close()

        if len(graph.nodes) <= 1 and not graph.edges:
            return ToolResult(
                ok=True,
                output=f"No provenance found for {args.node_id!r} — node may not exist in atoms.db.",
                metadata={"node_id": args.node_id, "nodes": 0, "edges": 0},
            )

        if fmt == "json":
            import json
            d = graph.to_dict()
            return ToolResult(
                ok=True,
                output=json.dumps(d, indent=2),
                metadata={"node_id": args.node_id, "nodes": len(graph.nodes), "edges": len(graph.edges)},
            )

        if fmt == "summary":
            edge_types: dict[str, int] = {}
            for edge in graph.edges:
                edge_types[edge.label] = edge_types.get(edge.label, 0) + 1
            type_str = ", ".join(f"{k}: {v}" for k, v in sorted(edge_types.items()))
            summary = (
                f"Provenance of {args.node_id}:\n"
                f"  nodes: {len(graph.nodes)}\n"
                f"  edges: {len(graph.edges)}\n"
                f"  max depth reached: {graph.max_depth_reached}\n"
                f"  edge types: {type_str or '(none)'}\n"
                + ("  (truncated — increase depth to see more)\n" if graph.truncated else "")
            )
            return ToolResult(
                ok=True,
                output=summary,
                metadata={"node_id": args.node_id, "nodes": len(graph.nodes), "edges": len(graph.edges)},
            )

        # Default: tree
        rendered = graph.render()
        if graph.truncated:
            rendered += f"\n(truncated at depth {graph.max_depth_reached} — use depth={args.depth + 5} to see more)"
        return ToolResult(
            ok=True,
            output=rendered,
            metadata={
                "node_id": args.node_id,
                "nodes": len(graph.nodes),
                "edges": len(graph.edges),
                "truncated": graph.truncated,
            },
        )
