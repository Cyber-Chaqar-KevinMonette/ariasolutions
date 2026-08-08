#!/usr/bin/env python3
import re

with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/loop.py', 'r') as f:
    content = f.read()

old_text = '''                # ── Tier 3: approval-token gate ──────────────────────
                if meta.requires_approval:
                    try:
                        consume_grant(
                            event_id=args.get("_approval_event_id", ""),
                            tool_name=tool_name,
                            args=args,
                            trace_id=trace_id,
                        )
                    except ApprovalDenied as e:
                        req = request_approval(
                            tool_name=tool_name,
                            args=args,
                            justification=args.get("_justification", "(none provided)"),
                            trace_id=trace_id,
                        )'''

new_text = '''                # ── Tier 3: approval-token gate ──────────────────────
                if meta.requires_approval:
                    try:
                        consume_grant(
                            event_id=args.get("_approval_event_id", ""),
                            tool_name=tool_name,
                            args=args,
                            trace_id=trace_id,
                        )
                    except ApprovalDenied:
                        # Check for learned approval patterns before asking human
                        try:
                            from .approval_patterns import check_approval_pattern
                            auto_approved, pattern = check_approval_pattern(
                                tool_name, args
                            )
                            if auto_approved and pattern is not None:
                                # Auto-approve based on learned pattern
                                _record("approval-d", {
                                    "tool": tool_name,
                                    "reason": f"auto-approved via pattern {pattern.pattern_id}",
                                    "pattern_id": pattern.pattern_id,
                                })
                                messages.append({
                                    "role": "tool", "name": tool_name,
                                    "content": f"auto-approved (pattern: {pattern.pattern_id})",
                                })
                                continue
                        except Exception:
                            pass  # Pattern check failed, fall through to human approval

                        req = request_approval(
                            tool_name=tool_name,
                            args=args,
                            justification=args.get("_justification", "(none provided)"),
                            trace_id=trace_id,
                        )'''

if old_text in content:
    content = content.replace(old_text, new_text)
    with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/loop.py', 'w') as f:
        f.write(content)
    print("Successfully patched loop.py")
else:
    print("Could not find the exact text to replace")
    print("Looking for:")
    print(repr(old_text[:200]))