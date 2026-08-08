# SCANNER_CATALOG.md — 100 scanners to keep Aria's vessel honest

> Kevin's signal: *"consider up to 100 more scanners we could invaluably add."* This is the
> living catalog. Each is propose-only, Tier-1, and (where possible) reuses the `scan_text`
> line engine in `path_scan/scanner.py`. Build the **Tier-A** ten first; the rest are
> sequenced behind them. `block` = must not apply · `warn` = review · `info` = worth knowing.
>
> Anti-ghost / anti-zombie / anti-false-path is the spine: **nothing dead, nothing fake,
> nothing pointing at the wrong place** ever reaches Aria or Kevin.

## Tier-A — build next (highest leverage, lowest cost)

1. **secret-leak** — API keys, tokens, private keys, `password=…`, AWS/Slack/OpenAI key shapes in shipped code. `block`.
2. **anchor-integrity** — every `-import-d` / `-all-d` anchor referenced by an apply script actually exists in the target; every `__all__` name has a backing symbol. `block`.
3. **import-cycle** — circular imports within `sovereign_agent.*` (AST import graph). `warn`.
4. **dead-symbol** — functions/classes defined in shipped code, exported, never referenced anywhere (true orphans, distinct from public API). `warn`.
5. **authority-tier-drift** — a tool registered at a tier inconsistent with its `failure_modes`, or a Tier-3 tool missing `requires_approval=True`. `block`.
6. **time-bomb** — hardcoded dates/years, `datetime(2026, …)` literals, "expires"/"valid until" constants. `warn`.
7. **network-in-shipped** — `requests.`/`urllib`/`socket`/`httpx` calls in code paths that claim to be offline/local-only. `warn`.
8. **bare-except** — `except:` / `except Exception: pass` swallowing errors silently. `warn`.
9. **mutable-default-arg** — `def f(x=[])` / `={}` foot-guns. `warn`.
10. **test-determinism** — tests using wall-clock, real network, unseeded RNG, or `tmp` outside `tmp_path`. `warn`.

## Anti-false-path family (extends this module)

11. relative-path-escape — `../../` traversal in shipped path joins. `warn`.
12. symlink-target — payload symlinks pointing outside the module. `block`.
13. case-collision — paths differing only by case (breaks on case-insensitive FS). `warn`.
14. windows-path-literal — `C:\\` / backslash separators in cross-platform code. `warn`.
15. hardcoded-port — magic network ports with no config indirection. `info`.
16. data-dir-bypass — file writes not routed through `SETTINGS.paths.*`. `warn`.
17. sandbox-escape — writes outside `sandbox_dir` in `Mode.BUSY` paths (pairs with `pathguard`). `block`.
18. venv-assumption — hardcoded `.venv/bin/python` in shipped code (fine in scripts, not in src). `warn`.
19. glob-too-broad — `rglob("*")` / `shutil.rmtree` on a computed root. `warn`.
20. tmpfile-no-cleanup — `NamedTemporaryFile`/`mkdtemp` without cleanup. `info`.

## Anti-ghost family (structure that won't take effect)

21. orphan-payload-module — payload `.py` never imported by any `__init__`/apply. `warn`.
22. missing-test — shipped module with no `tests/test_*.py`. `warn`.
23. missing-readme — staged module with no `README.md`. `info`.
24. missing-apply — staged module with no `apply_*.sh`. `block`.
25. apply-source-missing — apply `cp` source path absent from payload. `block`.
26. apply-dest-outside-repo — apply `cp` destination outside `$REPO_ROOT`. `block`.
27. unregistered-sentinel — `Sentinel` subclass with no `@register_sentinel`. `warn`.
28. unregistered-tool — `*_tools.py` class never added to `tools/__all__`. `warn`.
29. duplicate-tool-id — two tools sharing a name/id. `block`.
30. dangling-anchor — `-import-d` anchor present but the imported symbol missing. `block`.
31. stale-doc-reference — docs naming a file/function/flag that no longer exists. `warn`.
32. empty-package — `__init__.py`-only package with no real payload. `info`.
33. shadowed-module — payload name colliding with an existing live module (silent override). `block`.
34. test-only-import — shipped module importing a dev/test-only dependency. `warn`.
35. unreachable-branch — `if False:` / post-`return` code. `info`.

## Anti-zombie family (dead matter accreting)

36. bak-sprawl — count/age of `*.bak.*` across the repo; flag when over a threshold. `warn`.
37. pycache-in-git — `__pycache__`/`.pyc` tracked or inside payload. `warn`.
38. orphan-backup-dir — `backups/` for a module no longer staged. `info`.
39. stale-snapshot — `.safe_apply_snapshot/` left behind after a completed apply. `info`.
40. drift — applied module whose live code diverged from its payload. `warn`.
41. duplicate-file — byte-identical files in multiple locations (copy-paste rot). `info`.
42. dead-test — `test_*` referencing a removed symbol (collection error). `block`.
43. skipped-test-rot — `@pytest.mark.skip` with no reason / very old. `info`.
44. commented-code-block — large blocks of commented-out code. `info`.
45. todo-debt — `TODO`/`FIXME`/`XXX` density per module (trend, not gate). `info`.

## Safety-kernel & doctrine scanners

46. deferred-unsafe-touch — edits to `mos_canon.py` clauses or the `DEFERRED_UNSAFE` catalog. `block`.
47. charter-hash-touch — any change to `SIGNAL.md` charter-hash header. `block`.
48. self-modify — code that writes to `src/sovereign_agent/**` at runtime (self-rewriting). `block`.
49. authority-bypass — code path reaching a tool without `check_authority`. `block`.
50. approval-bypass — Tier-3 action with no operator-approval gate. `block`.
51. rollback-coverage — a mutating action with no registered rollback generator. `warn`.
52. reversibility-claim — action labeled REVERSIBLE with no restore path. `warn`.
53. heal-without-lease — sentinel `heal()` acting without a `RepairLease`. `block`.
54. propose-only-violation — Tier-1 sentinel performing a write. `block`.
55. kill-switch-missing — sentinel with no per-id kill-switch env. `warn`.

## Quality / correctness scanners

56. docstring-coverage — public funcs/classes lacking docstrings (per-module %). `info`.
57. type-annotation-coverage — public signatures missing annotations. `info`.
58. complexity — cyclomatic complexity over threshold. `info`.
59. long-function — functions over N lines. `info`.
60. god-object — classes over N methods/attributes. `info`.
61. duplicate-logic — near-duplicate functions (token-shingle similarity). `info`.
62. magic-number — unexplained numeric literals in logic. `info`.
63. print-in-src — `print(` in shipped code instead of the event/log channel. `warn`.
64. breakpoint — `breakpoint()`/`pdb.set_trace()`/`import pdb` (also in godtier rubric). `block`.
65. assert-in-prod — `assert` used for runtime validation (stripped under `-O`). `warn`.
66. f-string-logging — eager f-string in hot logging paths. `info`.
67. encoding-bom — BOM / non-UTF-8 / mixed line endings. `warn`.
68. emoji-zwj — variation selectors / ZWJ (pairs with `aria-safe-glyphs`). `warn`.
69. tab-space-mix — mixed indentation (pairs with `validators`). `block`.
70. unicode-homoglyph — look-alike chars in identifiers/strings. `warn`.

## Resource / hardware scanners (energy-crisis lever)

71. vram-overcommit — heavy GPU tool with no `vram_lock` / over budget (pairs with `vram.py`). `block`.
72. unbounded-loop — `while True:` with no break/timeout in shipped code. `warn`.
73. unbounded-memory — unbounded list/dict growth in long-running loops. `warn`.
74. blocking-in-async — sync I/O / `time.sleep` inside `async def`. `warn`.
75. missing-timeout — network/subprocess calls without a timeout. `warn`.
76. large-payload — oversized binary/data files in a payload. `warn`.
77. heavy-import-toplevel — torch/numpy imported at module top in light paths. `info`.
78. recompute-no-cache — expensive pure call recomputed in a loop (cache candidate). `info`.
79. thread-unsafe-global — shared mutable global without a lock. `warn`.
80. fd-leak — files/sockets opened without context manager. `warn`.

## Memory / data-integrity scanners

81. atom-schema — atoms written off-schema (pairs with `atoms_compact`). `warn`.
82. chain-break — append-only chain with a non-linking write. `block`.
83. pii-in-memory — emails/phones/addresses stored unredacted. `warn`.
84. honey-atom-leak — honey-atom ids surfaced in normal recall (pairs with `phantom`). `block`.
85. provenance-missing — derived record without a parent pointer. `warn`.
86. catalog-orphan — sentinel catalog with no owning sentinel. `info`.
87. db-migration-gap — schema field read but never written (or vice versa). `warn`.
88. clock-skew — timestamps not UTC / not ISO-8601. `info`.
89. nondeterministic-hash — `hash()`/`set` ordering used for stable output. `warn`.
90. json-nonportable — `NaN`/`Infinity`/non-str keys serialized. `warn`.

## Meta / self-watching scanners

91. scanner-self-flag — a scanner that flags its own pattern table without a pragma (this module dogfoods it). `warn`.
92. false-positive-rate — track each scanner's overturn rate; auto-demote noisy ones. `info`.
93. coverage-of-coverage — modules/dirs no scanner reaches yet. `info`.
94. sentinel-health-stale — a sentinel whose last scan is too old. `info`.
95. anchor-namespace — anchor-id collisions across modules. `warn`.
96. apply-idempotency — apply script not safe to run twice. `block`.
97. test-isolation — module tests that mutate shared state / leak into siblings. `warn`.
98. license-header — shipped files missing the required header. `info`.
99. changelog-gap — applied module with no `CHANGELOG.md` entry. `info`.
100. regression-guard — a previously-fixed defect class reappearing (ties to the 14-gen catalog). `warn`.

---

### Build pattern
Most scanners are a regex/AST rule + a severity + a message, plugged into the existing
`scan_text` engine or a small AST visitor. New ones register as their own `@register_sentinel`
**or** as additional rules inside `PathSentinel` when they share the staged-module surface.
Always: propose-only, an `# scanner-id: allow` pragma for reviewed exemptions, real behavior
tests (prove it catches AND that it stays quiet on clean input), and wire the blocking ones
into `safe_apply` step 0.
