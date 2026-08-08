"""code_school — teach Kevin to read and write the system he already owns.

code-school-d (Kevin, 2026-08-04): "I finally want us to make a bot that
teaches me how to code... I want to learn more about building AI systems, to
where I can be a reliable programmer."

Four parts, each deliberately small:
  • tracks.py   — which languages exist, KEEP-list gated like verticals.py
  • lessons.py  — the curriculum, as data citing real files in this repo
  • drills.py   — exercises + the spaced-repetition schedule
  • runner.py   — grading, by executing the submission inside bwrap

The organising idea: generic tutorials teach syntax, but what makes someone
reliable is reading real code and debugging real failures. Kevin owns a
~100k-line production agent system, and on 2026-08-03/04 watched six real
bugs get found in it — every one of which looked healthy from the outside.
That is the curriculum, and nobody else could write it.
"""
from __future__ import annotations

__all__ = ["tracks", "lessons", "drills", "runner"]
