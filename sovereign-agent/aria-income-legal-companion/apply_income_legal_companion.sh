#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_income_legal_companion.sh — grants tracker, business funding
#  directory, consumer-law Q&A companion, Christian County lien-auction check
#
#  Kevin (2026-08-01): "add some kind of consumer law companion, add a
#  category for business loans... add liens in the real estate section for
#  title auctions... income securing category. For consumer law, loans, and
#  other stuff." Clarified: consumer law = informational Q&A only (not
#  advice, disclaimed); income securing = loans + grants + incentive
#  programs together; liens = a periodic seasonal check, not a continuous
#  poller.
#
#  Delivers:
#    - grants_tracker.py — GrantsGovFetcher (kind="grants-gov"), a REAL,
#      live, no-auth-required federal grants API (api.grants.gov/v1/api/
#      search2), curl-verified directly, not just documented.
#    - real_estate_lien_auctions.py — Christian County, KY's delinquent
#      tax-sale-date announcement page (verified live), weekly interval
#      per Kevin's own "seasonal check is fine" choice. Montgomery County
#      has no scraper here -- confirmed twice, live, nothing structured
#      exists on its Trustee page to scrape.
#    - business_funding_directory.py — curated, verified SBA program +
#      lender reference (not a live tracker; loan offers aren't "new
#      listings" the way retail/grants are).
#    - consumer_law_companion.py — deterministic keyword-routed answers
#      (FDCPA/FCRA/TILA/FCBA/ECOA), NOT free-form LLM legal advice --
#      wrong statute names are a real harm a stale price never is.
#    - New "INCOME SECURING" category (1 channel: business-grants, the
#      live grants.gov feed). Liens join the EXISTING REAL ESTATE category
#      as a new "lien-auctions" channel -- its own vertical slug (NOT
#      realestate-prefixed) so it bypasses the buy-box gate entirely
#      (a sale-date announcement has no price/location to filter on).
#    - /consumer-law and /funding slash commands (no channel needed --
#      Q&A and static reference content, not alerting content).
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
for f in grants_tracker.py real_estate_lien_auctions.py \
         business_funding_directory.py consumer_law_companion.py; do
  cp "$HERE/payload/src/sovereign_agent/$f" "$PKG/$f"
  echo "  ✓ $f"
done

echo "→ patching fetchers.py, verticals.py, discord_admin/blueprint.py, discord_admin/bot.py"
for f in discord_runtime/fetchers.py verticals.py discord_admin/blueprint.py discord_admin/bot.py; do
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


# ── fetchers.py: register Christian County tax-sale parser + grants-gov kind ──
f = pkg / "discord_runtime" / "fetchers.py"
patch(f, "def _parse_christian_county_tax_sale",
      'register_scrape_parser("montgomerytn.gov", _parse_montgomery_county_tn)\n',
      'register_scrape_parser("montgomerytn.gov", _parse_montgomery_county_tn)\n'
      '\n'
      '# lien-auction-d (Kevin, 2026-08-01): "add liens in the real estate\n'
      '# section for title auctions" -- Christian County KY delinquent\n'
      '# property tax sale date/registration deadline, verified live.\n'
      '# Weekly seasonal check per Kevin\'s own choice, not continuous.\n'
      'def _parse_christian_county_tax_sale(html: str, url: str) -> list[Item]:\n'
      '    from sovereign_agent.real_estate_lien_auctions import fetch_christian_county_tax_sale_items\n'
      '    return fetch_christian_county_tax_sale_items(html, url)\n'
      'register_scrape_parser("christiancountyky.gov", _parse_christian_county_tax_sale)\n',
      "fetchers.py Christian County tax-sale-date parser registration")

patch(f, 'kind == "grants-gov"',
      '    if kind == "warframe-flip":\n'
      '        return WarframeFlipFetcher(opener=opener, on_outcome=on_outcome)\n',
      '    if kind == "warframe-flip":\n'
      '        return WarframeFlipFetcher(opener=opener, on_outcome=on_outcome)\n'
      '    if kind == "grants-gov":\n'
      '        # income-securing-d (Kevin, 2026-08-01): a real, live,\n'
      '        # no-auth federal grants API -- POSTs a JSON body, so it\n'
      '        # needs its own Fetcher rather than HttpJsonFetcher (GET-only).\n'
      '        from sovereign_agent.grants_tracker import GrantsGovFetcher\n'
      '        return GrantsGovFetcher(opener=opener, on_outcome=on_outcome)\n',
      "fetchers.py grants-gov kind dispatch")

# ── verticals.py: lien-auctions source on a new (non-realestate-prefixed)
#    vertical inside the REAL ESTATE category, + a new business-grants
#    vertical under a new INCOME SECURING category ──────────────────────
v = pkg / "verticals.py"
patch(v, '_v("liens-christian-county"',
      '    _v("realestate-apartments", "Real Estate: Apartments", "🏠", 0x8B5E3C,\n',
      '    # lien-auction-d (Kevin, 2026-08-01): tax LIEN certificate sale\n'
      '    # announcements (buying the lien, not the property) -- a\n'
      '    # deliberately SEPARATE, non-"realestate-"-prefixed slug so it\n'
      '    # bypasses runtime.py\'s buy-box gate entirely (a sale-date\n'
      '    # announcement has no price/location to filter on). Still lives\n'
      '    # in the REAL ESTATE category via CATEGORY_SLUGS below.\n'
      '    _v("liens-christian-county", "Christian Co. KY Tax Lien Sale", "🔔",\n'
      '       0x8B5E3C, DEEP, "local",\n'
      '       [scrape("christian-co-tax-sale-date",\n'
      '               "https://christiancountyky.gov/tax-sale-date")],\n'
      '       ["tax lien", "delinquent tax", "certificate of delinquency"],\n'
      '       "Christian County, KY delinquent property tax sale date + "\n'
      '       "registration deadline — a seasonal check (weekly), not a "\n'
      '       "continuous poll; this content changes at most once a year.",\n'
      '       price=800, channel="lien-auctions"),\n'
      '    _v("realestate-apartments", "Real Estate: Apartments", "🏠", 0x8B5E3C,\n',
      "liens-christian-county vertical")

patch(v, '_v("business-grants"',
      ']\n\nCATALOG_BY_SLUG = {v.slug: v for v in CATALOG}',
      '    # income-securing-d (Kevin, 2026-08-01): "income securing\n'
      '    # category... loans, grants, and other stuff" (clarified: loans +\n'
      '    # grants + incentive programs together). Live tracker for the\n'
      '    # grants half via the real grants.gov API (curl-verified\n'
      '    # 2026-08-01, no auth needed); the loan/SBA half is a curated\n'
      '    # static reference (business_funding_directory.py) surfaced via\n'
      '    # /funding, not a live poll — loan offers aren\'t "new listings."\n'
      '    _v("business-grants", "Business Grants (grants.gov)", "💰",\n'
      '       0x2E8B57, DEEP, "online",\n'
      '       [("grants-gov-small-business",\n'
      '         "https://api.grants.gov/v1/api/search2?keyword=small+business"\n'
      '         "&oppStatuses=forecasted%7Cposted&postedDays=14", "grants-gov")],\n'
      '       ["grant", "funding opportunity", "sba", "small business"],\n'
      '       "Federal grant opportunities relevant to small business, "\n'
      '       "polled from grants.gov\'s real public API (posted in the last "\n'
      '       "14 days) — see also /funding for SBA loans + lender reference.",\n'
      '       price=800, channel="business-grants"),\n'
      ']\n\nCATALOG_BY_SLUG = {v.slug: v for v in CATALOG}',
      "business-grants vertical")

patch(v, '"INCOME SECURING":',
      '    "REAL ESTATE": ["realestate-single-family", "realestate-condos",\n'
      '                    "realestate-apartments"],\n',
      '    "REAL ESTATE": ["realestate-single-family", "realestate-condos",\n'
      '                    "realestate-apartments", "liens-christian-county"],\n'
      '    "INCOME SECURING": ["business-grants"],\n',
      "CATEGORY_SLUGS REAL ESTATE + INCOME SECURING entries")

patch(v, '"REAL ESTATE",\n    "INCOME SECURING",',
      '    "REAL ESTATE",\n)',
      '    "REAL ESTATE",\n    "INCOME SECURING",\n)',
      "SUBSCRIBABLE_CATEGORIES INCOME SECURING entry")

# ── discord_admin/blueprint.py: new INCOME SECURING category ────────────
b = pkg / "discord_admin" / "blueprint.py"
patch(b, 'CategorySpec("INCOME SECURING"',
      '            CategorySpec("REAL ESTATE", read_only=True,\n',
      '            # income-securing-d (Kevin, 2026-08-01): grants.gov live\n'
      '            # tracker feed; SBA/lender reference lives in /funding,\n'
      '            # not a channel — static content isn\'t "alerts."\n'
      '            CategorySpec("INCOME SECURING", read_only=True,\n'
      '                         channels=_category_channels("INCOME SECURING")),\n'
      '            CategorySpec("REAL ESTATE", read_only=True,\n',
      "CategorySpec INCOME SECURING")

# ── discord_admin/bot.py: /consumer-law and /funding slash commands ─────
bt = pkg / "discord_admin" / "bot.py"
patch(bt, '"/consumer-law"',
      '    ("/ask", "Ask Aria anything — the shop, the bots, or just to chat.", "everyone"),\n',
      '    ("/ask", "Ask Aria anything — the shop, the bots, or just to chat.", "everyone"),\n'
      '    ("/consumer-law", "⚖️ Consumer-law info (debt collection, credit reports, loans) — general info, not legal advice.", "everyone"),\n'
      '    ("/funding", "💰 Business funding reference — SBA loans, state grant portals, lender resources.", "everyone"),\n',
      "bot.py COMMANDS catalog entries for /consumer-law and /funding")

patch(bt, 'name="consumer-law"',
      '        @tree.command(name="ask",\n',
      '        @tree.command(name="consumer-law",\n'
      '                      description="Consumer-law info (debt collection, credit "\n'
      '                                  "reports, loans) — general info, not legal advice.")\n'
      '        async def consumer_law(interaction, question: str):\n'
      '            # everyone may ask — deterministic, no LLM call, no rate limit needed\n'
      '            from sovereign_agent.consumer_law_companion import answer_consumer_law_question\n'
      '            ans = answer_consumer_law_question(question)\n'
      '            from sovereign_agent.discord_limits import split_text\n'
      '            parts = split_text(ans.as_text(), 1900) or ["💛"]\n'
      '            await interaction.response.send_message(parts[0], ephemeral=False)\n'
      '            for part in parts[1:4]:\n'
      '                await interaction.followup.send(part)\n'
      '\n'
      '        @tree.command(name="funding",\n'
      '                      description="Business funding reference — SBA loans, "\n'
      '                                  "state grant portals, lender resources.")\n'
      '        async def funding(interaction):\n'
      '            from sovereign_agent.business_funding_directory import (\n'
      '                GENERAL_LENDERS, SBA_PROGRAMS, STATE_INCENTIVE_PORTALS)\n'
      '            lines = ["**SBA Loan Programs**"]\n'
      '            for p in SBA_PROGRAMS:\n'
      '                lines.append(f"• **{p.name}** — {p.note} ({p.url})")\n'
      '            lines.append("\\n**State Grant Portals**")\n'
      '            for p in STATE_INCENTIVE_PORTALS:\n'
      '                lines.append(f"• **{p.name}** — {p.note} ({p.url})")\n'
      '            lines.append("\\n**General Resources**")\n'
      '            for p in GENERAL_LENDERS:\n'
      '                url_part = f" ({p.url})" if p.url else ""\n'
      '                lines.append(f"• **{p.name}** — {p.note}{url_part}")\n'
      '            lines.append("\\nSee also #business-grants for live federal grant listings.")\n'
      '            from sovereign_agent.discord_limits import split_text\n'
      '            parts = split_text("\\n".join(lines), 1900) or ["💛"]\n'
      '            await interaction.response.send_message(parts[0], ephemeral=False)\n'
      '            for part in parts[1:4]:\n'
      '                await interaction.followup.send(part)\n'
      '\n'
      '        @tree.command(name="ask",\n',
      "bot.py /consumer-law and /funding commands")

print("→ compile check")
import py_compile
for rel in ("discord_runtime/fetchers.py", "verticals.py",
            "discord_admin/blueprint.py", "discord_admin/bot.py",
            "grants_tracker.py", "real_estate_lien_auctions.py",
            "business_funding_directory.py", "consumer_law_companion.py"):
    py_compile.compile(str(pkg / rel), doraise=True)
print("  ✓ all patched/new files compile")
PYEOF

echo "→ installing tests"
for f in test_grants_tracker.py test_real_estate_lien_auctions.py \
         test_business_funding_directory.py test_consumer_law_companion.py; do
  cp "$HERE/tests/$f" "$ROOT/tests/$f"
  echo "  ✓ tests/$f"
done
mkdir -p "$ROOT/tests/fixtures"
cp "$HERE/tests/fixtures/grants_search2_sample.json" "$ROOT/tests/fixtures/"
cp "$HERE/tests/fixtures/christian_co_tax_sale_date.html" "$ROOT/tests/fixtures/"
echo "  ✓ tests/fixtures/{grants_search2_sample.json,christian_co_tax_sale_date.html}"
python3 -m py_compile "$ROOT"/tests/test_grants_tracker.py \
                      "$ROOT"/tests/test_real_estate_lien_auctions.py \
                      "$ROOT"/tests/test_business_funding_directory.py \
                      "$ROOT"/tests/test_consumer_law_companion.py
echo "  ✓ tests compile"

echo
echo "✓ done."
echo "  Run: .venv/bin/python -m pytest tests/test_grants_tracker.py \\"
echo "         tests/test_real_estate_lien_auctions.py tests/test_business_funding_directory.py \\"
echo "         tests/test_consumer_law_companion.py -q"
echo
echo "  IMPORTANT: adding a new Discord category (INCOME SECURING) + a new"
echo "  channel in REAL ESTATE (lien-auctions) will change test_discord_admin.py's"
echo "  hardcoded create_category/create_channel/create_role counts. Run"
echo "  tests/test_discord_admin.py after applying and update the 4 assertion"
echo "  lines (search 'create_category\") ==', 'create_channel\") ==',"
echo "  'create_role\") ==') to whatever the test actually reports — do NOT"
echo "  guess the numbers, let the failing assertion tell you the real delta."
echo
echo "  After applying: sov scout sync (registers the 2 new sources), then"
echo "  /setup-shop in Discord (or /server setup from the cockpit) to create"
echo "  the new category/channels, then /setup-webhooks for the new channels."
echo
