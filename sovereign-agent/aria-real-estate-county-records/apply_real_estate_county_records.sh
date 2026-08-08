#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_real_estate_county_records.sh — county public-record sourcing +
#  flip-connections directory for the REAL ESTATE tracker
#
#  Kevin (2026-08-01), after ruling out Reddit (his account is banned, so the
#  reddit-oauth-d fix the rest of the fleet needs isn't an option for him
#  personally): "county public records for christian county and montgomery
#  county... have each post list the location and county per post... have
#  the bot explain how each property can be flipped and all the connections
#  to get it flipped immediately."
#
#  Delivers:
#    - real_estate_county_records.py — parsers for Christian County, KY
#      (Master Commissioner sale listings) and Montgomery County, TN
#      (Clerk & Master upcoming sales), verified against REAL live HTML
#      (fetched directly, not guessed) — the "easy" category from the
#      sourcing research: unauthenticated, structured, static, no
#      login/CAPTCHA. Tax-delinquent rolls (seasonal-only, no persistent
#      URL) and probate (docket-search only) are deliberately NOT
#      automated — no stable structured source exists for either.
#    - real_estate_connections.py — a small, curated "who to contact to
#      flip this" directory keyed to the strategy suggest_strategy()
#      already returns. Deliberately NOT the ~60-site list Kevin pasted
#      from another tool's research — most of those are unverifiable SEO
#      content, not something to hand him as vetted.
#    - real_estate_gate.py (overlay) — appends the connections line to
#      the existing strategy note; every existing caller picks it up for
#      free, no other file needs to change.
#    - fetchers.py — registers the 2 new host parsers (kind="scrape",
#      same mechanism as Target/Best Buy — task #228/#229).
#    - verticals.py — the 2 new sources join the EXISTING
#      realestate-single-family vertical/channel (not a new category —
#      avoids the Discord-blueprint/role scaffolding and its fragile
#      hardcoded test counts for a change this narrow).
#
#  Idempotent. Backs up every file it patches before touching it.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${1:-$PWD}"

if [[ ! -f "$ROOT/src/sovereign_agent/cli.py" ]]; then
  d="$PWD"
  while [[ "$d" != "/" ]]; do
    [[ -f "$d/src/sovereign_agent/cli.py" ]] && { ROOT="$d"; break; }
    d="$(dirname "$d")"
  done
fi
[[ -f "$ROOT/src/sovereign_agent/cli.py" ]] || { echo "✗ run from repo root"; exit 1; }
echo "◊ repo root: $ROOT"

PKG="$ROOT/src/sovereign_agent"
ts(){ date +%Y%m%d%H%M%S; }

echo "→ installing new payload modules"
for f in real_estate_county_records.py real_estate_connections.py; do
  cp "$HERE/payload/src/sovereign_agent/$f" "$PKG/$f"
  echo "  ✓ $f"
done

echo "→ overlaying real_estate_gate.py (adds connections to the strategy note)"
cp "$PKG/real_estate_gate.py" "$PKG/real_estate_gate.py.bak.$(ts)"
cp "$HERE/payload/src/sovereign_agent/real_estate_gate.py" "$PKG/real_estate_gate.py"
echo "  ✓ real_estate_gate.py"

echo "→ patching fetchers.py, verticals.py"
for f in discord_runtime/fetchers.py verticals.py; do
  cp "$PKG/$f" "$PKG/$f.bak.$(ts)"
done

python3 - "$PKG" <<'PYEOF'
import sys, pathlib

pkg = pathlib.Path(sys.argv[1])


def patch(path: pathlib.Path, already: str, old: str, new: str, label: str) -> None:
    src = path.read_text(encoding="utf-8")
    if already in src:
        print(f"  ↷ {label} already present — skipping")
        return
    if old not in src:
        print(f"✗ anchor not found for {label} in {path}", file=sys.stderr)
        sys.exit(1)
    src = src.replace(old, new, 1)
    path.write_text(src, encoding="utf-8")
    print(f"  ✓ {label}")


# ── fetchers.py: register the 2 county-record parsers by hostname ───────
f = pkg / "discord_runtime" / "fetchers.py"
patch(f, "christiancountymastercommissioner.com",
      'register_scrape_parser("www.dollargeneral.com", _parse_dollargeneral)\n',
      'register_scrape_parser("www.dollargeneral.com", _parse_dollargeneral)\n'
      '\n'
      '# county-records-d (Kevin, 2026-08-01): "county public records for\n'
      '# christian county and montgomery county" -- real, verified-live\n'
      '# court-listing pages (foreclosure/tax-sale), not guessed. Reddit\n'
      "# ruled out (Kevin's account is banned).\n"
      'def _parse_christian_county_ky(html: str, url: str) -> list[Item]:\n'
      '    from sovereign_agent.real_estate_county_records import fetch_christian_county_items\n'
      '    return fetch_christian_county_items(html, url)\n'
      'register_scrape_parser("christiancountymastercommissioner.com", _parse_christian_county_ky)\n'
      '\n'
      'def _parse_montgomery_county_tn(html: str, url: str) -> list[Item]:\n'
      '    from sovereign_agent.real_estate_county_records import fetch_montgomery_county_items\n'
      '    return fetch_montgomery_county_items(html, url)\n'
      'register_scrape_parser("montgomerytn.gov", _parse_montgomery_county_tn)\n',
      "fetchers.py county-record parser registration")

# ── verticals.py: add the 2 county-record sources to the existing
#    realestate-single-family vertical (reuses its channel; no new
#    Discord category/role scaffolding needed for a change this narrow) ─
v = pkg / "verticals.py"
patch(v, 'scrape("realestate-christian-county-ky"',
      '    _v("realestate-single-family", "Real Estate: Single-Family", "🏠",\n'
      '       0x8B5E3C, DEEP, "local",\n'
      '       [reddit_sub("realestateinvesting"),\n'
      '        reddit_search("realestateinvesting", "single family motivated seller"),\n'
      '        reddit_search("Wholesaling", "single family")],\n',
      '    _v("realestate-single-family", "Real Estate: Single-Family", "🏠",\n'
      '       0x8B5E3C, DEEP, "local",\n'
      '       [reddit_sub("realestateinvesting"),\n'
      '        reddit_search("realestateinvesting", "single family motivated seller"),\n'
      '        reddit_search("Wholesaling", "single family"),\n'
      '        # county-records-d (Kevin, 2026-08-01): real county court\n'
      '        # listings, Christian Co KY + Montgomery Co TN -- verified-live\n'
      '        # HTML, not guessed. Reddit ruled out (Kevin banned).\n'
      '        scrape("realestate-christian-county-ky",\n'
      '               "https://christiancountymastercommissioner.com/listings/"),\n'
      '        scrape("realestate-montgomery-county-tn",\n'
      '               "https://montgomerytn.gov/chancery/upcoming-clerk-and-master-sales")],\n',
      "verticals.py county-record sources on realestate-single-family")

print("→ compile check")
import py_compile
for rel in ("discord_runtime/fetchers.py", "verticals.py",
            "real_estate_gate.py", "real_estate_county_records.py",
            "real_estate_connections.py"):
    py_compile.compile(str(pkg / rel), doraise=True)
print("  ✓ all patched/new files compile")
PYEOF

echo "→ installing tests"
for f in test_real_estate_county_records.py test_real_estate_connections.py \
         test_real_estate_gate_connections.py; do
  cp "$HERE/tests/$f" "$ROOT/tests/$f"
  echo "  ✓ tests/$f"
done
mkdir -p "$ROOT/tests/fixtures"
cp "$HERE/tests/fixtures/christian_co_sample.html" "$ROOT/tests/fixtures/"
cp "$HERE/tests/fixtures/montgomery_tn_sample.html" "$ROOT/tests/fixtures/"
echo "  ✓ tests/fixtures/{christian_co_sample,montgomery_tn_sample}.html"
# test_real_estate_county_records.py imports fixtures via Path(__file__).parent
# / "fixtures" -- point it at tests/fixtures/ (already correct, same layout).
python3 -m py_compile "$ROOT"/tests/test_real_estate_county_records.py \
                      "$ROOT"/tests/test_real_estate_connections.py \
                      "$ROOT"/tests/test_real_estate_gate_connections.py
echo "  ✓ tests compile"

echo
echo "✓ done."
echo "  Run: .venv/bin/python -m pytest tests/test_real_estate_county_records.py \\"
echo "         tests/test_real_estate_connections.py tests/test_real_estate_gate_connections.py \\"
echo "         tests/test_real_estate_gate.py -q"
echo
echo "  These 2 sources are polled via kind=scrape (same hardened mechanism as"
echo "  Target/Best Buy) -- no Reddit involved, no rate-limit exposure from the"
echo "  fleet-wide 429 issue. They post into the EXISTING #single-family"
echo "  channel; sov scout sync isn't needed for a source addition to an"
echo "  already-synced vertical."
echo
echo "  Still open: tax-delinquent lists (seasonal-only, no persistent URL in"
echo "  either county) and probate (docket-search only) were deliberately NOT"
echo "  automated -- no stable structured source exists for either. A manual"
echo "  periodic check is the honest alternative, not a scraper that would"
echo "  silently do nothing most of the year."
echo
