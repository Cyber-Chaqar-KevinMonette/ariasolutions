#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_real_estate_edmonson.sh — Edmonson County, KY (Brownsville) Master
#  Commissioner scraper, a 3rd source for the existing realestate-single-
#  family vertical.
#
#  Kevin (2026-08-01): "extend the real estate radar to a few good and
#  active real estate communities" -- diagnosed first that condos/apartments
#  were 100% Reddit-sourced (dead: fleet-wide rate-limited, and Kevin is
#  banned from Reddit so the OAuth fix isn't available to him) while
#  single-family worked fine via its 2 county-record scrapers. Went looking
#  for more counties near Hopkinsville/Clarksville/Nashville with the same
#  kind of scrapable public listing page. Most small nearby counties
#  (Trigg, Todd, Logan, Caldwell) have no discoverable dedicated site.
#  Two real candidates from the official Kentucky Court of Justice master-
#  commissioner directory: Warren County's page renders via JavaScript
#  (confirmed by direct curl -- zero listing rows in the raw HTML), needs
#  the heavier Playwright-based fetcher, left as a follow-up. Edmonson
#  County's site (Weebly-built) is genuinely server-rendered -- curled
#  directly, found a real listing verbatim.
#
#  Delivers:
#    - real_estate_edmonson_county.py — parse_edmonson_county_ky() +
#      fetch_edmonson_county_items(), reusing CountyListing from
#      real_estate_county_records.py. Correctly yields zero listings for
#      a "SALE CANCELLED" block instead of posting a stale case row.
#    - fetchers.py: registers the edmonsoncountymastercommissioner.com
#      scrape parser.
#    - verticals.py: adds a 3rd scrape() source to the EXISTING
#      realestate-single-family vertical (same channel, no new category).
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

if pgrep -af "cockpit" 2>/dev/null | grep -E "bin/sovereign cockpit|sovereign_agent.*cockpit|[s]overeign cockpit" | grep -vE "pgrep|grep|apply_|bash -c" >/dev/null; then
  echo "✗ cockpit running. Stop it first."; exit 1
fi

PKG="$ROOT/src/sovereign_agent"
ts(){ date +%Y%m%d%H%M%S; }

echo "→ installing new payload module"
cp "$HERE/payload/src/sovereign_agent/real_estate_edmonson_county.py" "$PKG/real_estate_edmonson_county.py"
echo "  ✓ real_estate_edmonson_county.py"

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


# ── fetchers.py: register the Edmonson County scrape parser ──
f = pkg / "discord_runtime" / "fetchers.py"
patch(f, "def _parse_edmonson_county_ky",
      'register_scrape_parser("christiancountyky.gov", _parse_christian_county_tax_sale)\n',
      'register_scrape_parser("christiancountyky.gov", _parse_christian_county_tax_sale)\n\n'
      '# edmonson-county-d (Kevin, 2026-08-01): "extend the real estate\n'
      '# radar to a few good and active real estate communities" --\n'
      '# Edmonson County KY (Brownsville), confirmed real + server-\n'
      '# rendered (curled directly), a 3rd source for single-family.\n'
      'def _parse_edmonson_county_ky(html: str, url: str) -> list[Item]:\n'
      '    from sovereign_agent.real_estate_edmonson_county import fetch_edmonson_county_items\n'
      '    return fetch_edmonson_county_items(html, url)\n'
      'register_scrape_parser("www.edmonsoncountymastercommissioner.com", _parse_edmonson_county_ky)\n',
      "register Edmonson County scrape parser")

# ── verticals.py: 3rd scrape() source on realestate-single-family ──
v = pkg / "verticals.py"
patch(v, 'scrape("realestate-edmonson-county-ky"',
      '        scrape("realestate-montgomery-county-tn",\n'
      '               "https://montgomerytn.gov/chancery/upcoming-clerk-and-master-sales")],\n',
      '        scrape("realestate-montgomery-county-tn",\n'
      '               "https://montgomerytn.gov/chancery/upcoming-clerk-and-master-sales"),\n'
      '        # edmonson-county-d (Kevin, 2026-08-01): 3rd county source,\n'
      '        # same real-record pattern -- server-rendered, confirmed live.\n'
      '        scrape("realestate-edmonson-county-ky",\n'
      '               "https://www.edmonsoncountymastercommissioner.com/sale-dates.html")],\n',
      "realestate-single-family: 3rd scrape() source (Edmonson County)")
PYEOF

echo "→ Compile check..."
"$ROOT/.venv/bin/python" -m py_compile "$PKG/real_estate_edmonson_county.py" \
  "$PKG/discord_runtime/fetchers.py" "$PKG/verticals.py"

mkdir -p "$ROOT/tests/fixtures"
cp "$HERE/tests/test_real_estate_edmonson.py" "$ROOT/tests/"
cp "$HERE/tests/fixtures/edmonson_active.html" "$HERE/tests/fixtures/edmonson_cancelled.html" "$ROOT/tests/fixtures/"

echo "Running tests..."
"$ROOT/.venv/bin/python" -m pytest "$ROOT/tests/test_real_estate_edmonson.py" \
  "$ROOT/tests/test_verticals.py" "$ROOT/tests/test_discord_runtime.py" -q || \
  { echo "APPLY-FAIL: applied tests did not pass"; exit 1; }
echo "=== aria-realestate-edmonson-county applied 💛 ==="
