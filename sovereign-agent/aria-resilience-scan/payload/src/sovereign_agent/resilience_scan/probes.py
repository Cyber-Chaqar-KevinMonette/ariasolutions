"""resilience_scan/probes.py — the edge-case input battery.

God-tier resilience means a system never wedges on a weird input — it degrades to a clear value or status.
This battery generates the adversarial / boundary inputs every robust function must survive: empty, None,
huge, malformed, unicode, negative, zero, whitespace, deeply-nested. Works for any callable on either layer.
"""
from __future__ import annotations


def edge_strings() -> list:
    """Edge-case string inputs."""
    return [
        "",                      # empty
        " ",                     # whitespace
        "\n\t  \n",              # only whitespace/newlines
        "a" * 100_000,           # huge
        "🌐你好🔥​﻿",   # unicode / zero-width / BOM
        "'; DROP TABLE x; --",   # injection-ish
        "../../etc/passwd",      # path-ish
        "\x00\x01\x02",          # control bytes
        "}{][)(<>",              # unbalanced symbols
    ]


def edge_lists() -> list:
    """Edge-case list inputs."""
    return [
        [],                      # empty
        [""],                    # one empty string
        list(range(10_000)),     # huge
        [None, None],            # Nones
        ["a"] * 5000,            # large dup
    ]


def edge_numbers() -> list:
    return [0, -1, -0.0, 1e18, -1e18, float("inf"), float("-inf")]


def edge_any() -> list:
    """A mixed bag for callables of unknown signature."""
    return [None, "", [], {}, 0, False]
