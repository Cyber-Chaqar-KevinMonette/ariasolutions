#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_real_estate.sh — Aria gains a Real Estate deal-tracker
#
#  Delivers:
#    - real_estate_deal_analyzer.py  — the long-term math (payback period,
#                                      monthly cash flow at low/mid/high rent)
#    - real_estate_requirements.py   — Kevin's own buy-box criteria (set via
#                                      the #requirements channel)
#    - real_estate_strategy.py       — free, deterministic financing/closing
#                                      strategy suggestions (#secure-deals)
#    - real_estate_gate.py           — the narrow runtime hook tying it together
#    - a REAL ESTATE category: #single-family, #condos, #apartments,
#      #secure-deals, #requirements
#
#  Scope, flagged for Kevin's own review: v1 sources are Reddit real-estate/
#  wholesaling subreddits ONLY — free, already-proven mechanism (same OAuth
#  fetcher + is_actionable noise filter as #222/#224). Zillow/Redfin/
#  Realtor.com scraping is deliberately NOT included: stealth_browser.py
#  self-documents it can't reliably clear that tier of WAF, and MLS/Zillow
#  ToS + CFAA exposure has no existing precedent in this codebase. County/
#  HUD/USDA open-data feeds are a natural free follow-up once Kevin names
#  his target county's real portal URL (never guessed/fabricated here).
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
for f in real_estate_deal_analyzer.py real_estate_requirements.py \
         real_estate_strategy.py real_estate_gate.py; do
  cp "$HERE/payload/src/sovereign_agent/$f" "$PKG/$f"
  echo "  ✓ $f"
done

echo "→ patching verticals.py, blueprint.py, runtime.py, bot.py, test_discord_admin.py"
for f in verticals.py discord_admin/blueprint.py discord_runtime/runtime.py discord_admin/bot.py; do
  cp "$PKG/$f" "$PKG/$f.bak.$(ts)"
done
cp "$ROOT/tests/test_discord_admin.py" "$ROOT/tests/test_discord_admin.py.bak.$(ts)"

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


# ── verticals.py ────────────────────────────────────────────────────────
v = pkg / "verticals.py"

patch(v, "geo_filter_enabled: bool = False",
      '    blurb: str = ""\n',
      '    blurb: str = ""\n'
      '    # zip/radius descope (Kevin, 2026-07-29): "we really only need\n'
      '    # the zip radius as an optional feature per tracker... for TCGs\n'
      '    # that is what we most need it for and squishmallows." Off by\n'
      '    # default; only verticals tied to physical pickup turn it on.\n'
      '    geo_filter_enabled: bool = False\n',
      "Vertical.geo_filter_enabled field")

patch(v, "def _v(slug, name, emoji, color, tier, lane, sources, kws, blurb,\n"
         "       price=700, channel=\"\", excludes=None, geo_filter_enabled=False):",
      'def _v(slug, name, emoji, color, tier, lane, sources, kws, blurb,\n'
      '       price=700, channel="", excludes=None):\n'
      '    return Vertical(slug=slug, name=name, emoji=emoji, color=color, tier=tier,\n'
      '                    lane=lane, sources=sources, rank_keywords=kws, blurb=blurb,\n'
      '                    price_cents=price, channel=channel,\n'
      '                    excludes=excludes if excludes is not None\n'
      '                    else list(COMMON_EXCLUDES))\n',
      'def _v(slug, name, emoji, color, tier, lane, sources, kws, blurb,\n'
      '       price=700, channel="", excludes=None, geo_filter_enabled=False):\n'
      '    return Vertical(slug=slug, name=name, emoji=emoji, color=color, tier=tier,\n'
      '                    lane=lane, sources=sources, rank_keywords=kws, blurb=blurb,\n'
      '                    price_cents=price, channel=channel,\n'
      '                    excludes=excludes if excludes is not None\n'
      '                    else list(COMMON_EXCLUDES),\n'
      '                    geo_filter_enabled=geo_filter_enabled)\n',
      "_v() geo_filter_enabled param")

patch(v, 'geo_filter_enabled=True),\n    _v("mtg"',
      '"Pokémon restocks + deals, ranked by set value.", price=800),\n',
      '"Pokémon restocks + deals, ranked by set value.", price=800,\n'
      '       geo_filter_enabled=True),\n',
      "pokemon (star) geo_filter_enabled")

for anchor_channel, label in [
    ('channel="pokemon"),', "bestbuy-pokemon geo_filter_enabled"),
    ('channel="target-pokemon"),', "target-pokemon geo_filter_enabled"),
    ('channel="squishmallows"),', "target-squishmallows geo_filter_enabled"),
    ('channel="samsclub-squishmallows"),', "samsclub-squishmallows geo_filter_enabled"),
    ('channel="samsclub-pokemon"),', "samsclub-pokemon geo_filter_enabled"),
    ('channel="costco-squishmallows"),', "costco-squishmallows geo_filter_enabled"),
    ('channel="costco-pokemon"),', "costco-pokemon geo_filter_enabled"),
    ('channel="dg-pokemon"),', "dollargeneral-pokemon geo_filter_enabled"),
]:
    new_channel = anchor_channel[:-2] + ", geo_filter_enabled=True),"
    patch(v, new_channel, anchor_channel, new_channel, label)

patch(v, '_v("realestate-single-family"',
      ']\n\nCATALOG_BY_SLUG = {v.slug: v for v in CATALOG}',
      '    # 🏠 REAL ESTATE category (Kevin, 2026-07-28/29): deal-sourcing\n'
      '    # for off-market/motivated-seller leads, split by property type.\n'
      '    # v1 deliberately uses only free, low-legal-risk sources — real\n'
      '    # estate/wholesaling subreddits (same OAuth fetcher + is_actionable\n'
      '    # noise filter already proven for #222/#224) — NOT Zillow/Redfin/\n'
      '    # Realtor.com scraping (stealth_browser.py self-documents it can\'t\n'
      '    # reliably clear that tier of WAF, and MLS/Zillow ToS + CFAA\n'
      '    # exposure has no existing precedent here). County/HUD/USDA public\n'
      '    # open-data feeds are a free follow-up once Kevin names his target\n'
      '    # county\'s real portal URL.\n'
      '    _v("realestate-single-family", "Real Estate: Single-Family", "🏠",\n'
      '       0x8B5E3C, DEEP, "local",\n'
      '       [reddit_sub("realestateinvesting"),\n'
      '        reddit_search("realestateinvesting", "single family motivated seller"),\n'
      '        reddit_search("Wholesaling", "single family")],\n'
      '       ["motivated seller", "must sell", "as-is", "pre-foreclosure",\n'
      '        "inherited", "wholesale"],\n'
      '       "Off-market single-family leads — motivated-seller and wholesale "\n'
      '       "signals from real-estate investing communities.",\n'
      '       price=800, channel="single-family"),\n'
      '    _v("realestate-condos", "Real Estate: Condos", "🏠", 0x8B5E3C, DEEP,\n'
      '       "local",\n'
      '       [reddit_search("realestateinvesting", "condo"),\n'
      '        reddit_search("RealEstate", "condo motivated seller")],\n'
      '       ["condo", "hoa", "motivated seller", "must sell"],\n'
      '       "Condo leads — motivated-seller signals from real-estate "\n'
      '       "communities.",\n'
      '       price=800, channel="condos"),\n'
      '    _v("realestate-apartments", "Real Estate: Apartments", "🏠", 0x8B5E3C,\n'
      '       DEEP, "local",\n'
      '       [reddit_sub("Landlord"),\n'
      '        reddit_search("realestateinvesting", "multifamily"),\n'
      '        reddit_search("realestateinvesting", "apartment building")],\n'
      '       ["multifamily", "apartment", "duplex", "triplex", "fourplex",\n'
      '        "motivated seller"],\n'
      '       "Apartment/multifamily leads — duplex through larger multifamily, "\n'
      '       "motivated-seller signals from real-estate communities.",\n'
      '       price=800, channel="apartments"),\n'
      ']\n\n'
      'CATALOG_BY_SLUG = {v.slug: v for v in CATALOG}',
      "REAL ESTATE verticals appended to CATALOG")

patch(v, '"REAL ESTATE":',
      '    "DOLLAR GENERAL": ["dollargeneral-pokemon"],\n',
      '    "DOLLAR GENERAL": ["dollargeneral-pokemon"],\n'
      '    "REAL ESTATE": ["realestate-single-family", "realestate-condos",\n'
      '                    "realestate-apartments"],\n',
      "CATEGORY_SLUGS REAL ESTATE entry")

patch(v, '"DOLLAR GENERAL",\n    "REAL ESTATE",',
      '    "DOLLAR GENERAL",\n)',
      '    "DOLLAR GENERAL",\n    "REAL ESTATE",\n)',
      "SUBSCRIBABLE_CATEGORIES REAL ESTATE entry")

# ── blueprint.py ─────────────────────────────────────────────────────────
b = pkg / "discord_admin" / "blueprint.py"
patch(b, 'CategorySpec("REAL ESTATE"',
      '            CategorySpec("DOLLAR GENERAL", read_only=True,\n'
      '                         channels=_category_channels("DOLLAR GENERAL")),\n',
      '            CategorySpec("DOLLAR GENERAL", read_only=True,\n'
      '                         channels=_category_channels("DOLLAR GENERAL")),\n'
      '            # real-estate-d (Kevin, 2026-07-28/29): deal-sourcing split\n'
      '            # by property type, plus a curated secure-deals channel and\n'
      '            # a requirements channel for Kevin\'s own buy-box criteria.\n'
      '            CategorySpec("REAL ESTATE", read_only=True,\n'
      '                         channels=_category_channels("REAL ESTATE") + [\n'
      '                ChannelSpec("secure-deals",\n'
      '                            topic="💰 Leads that clear your buy-box, with a "\n'
      '                                  "financing/closing strategy suggestion."),\n'
      '                ChannelSpec("requirements", allow_send_everyone=True,\n'
      '                            topic="📋 Set your buy-box: zip+radius, property "\n'
      '                                  "types, price range, min cash flow — "\n'
      '                                  "key=value (e.g. zips=90210 radius=20 "\n'
      '                                  "price_max=300000 min_cash_flow=200)."),\n'
      '            ]),\n',
      "CategorySpec REAL ESTATE")

# ── discord_runtime/runtime.py ───────────────────────────────────────────
r = pkg / "discord_runtime" / "runtime.py"
patch(r, "real-estate-gate-d",
      '                if source.kind == "rss":\n'
      '                    from sovereign_agent.actionability import is_actionable\n'
      '                    if not is_actionable(item.text, getattr(item, "url", "") or ""):\n'
      '                        report.filtered += 1\n'
      '                        report.no_signal_filtered += 1\n'
      '                        continue\n'
      '                key = f"{source.name}:{item.id}"\n'
      '                if key in self._seen:\n'
      '                    continue\n'
      '                self._seen.add(key)\n'
      '                alert = Alert(source=source.name, item_id=item.id,\n'
      '                              content=_format_alert(self.project, source, item),\n'
      '                              title=item.text,\n'
      '                              url=getattr(item, "url", "") or "",\n'
      '                              embed=getattr(item, "embed", None))\n',
      '                if source.kind == "rss":\n'
      '                    from sovereign_agent.actionability import is_actionable\n'
      '                    if not is_actionable(item.text, getattr(item, "url", "") or ""):\n'
      '                        report.filtered += 1\n'
      '                        report.no_signal_filtered += 1\n'
      '                        continue\n'
      '                # real-estate-gate-d (Kevin, 2026-07-29): a narrow,\n'
      '                # opt-in hook — only real-estate verticals get deal\n'
      '                # math + a buy-box gate; every other vertical\'s poll\n'
      '                # loop is untouched. Lazy import so a runtime with no\n'
      '                # real-estate verticals never pays this cost.\n'
      '                re_strategy_note = ""\n'
      '                proj_name = getattr(self.project, "project_name", "") or ""\n'
      '                if proj_name.startswith("scout-realestate-") and self._data_dir is not None:\n'
      '                    from sovereign_agent.real_estate_gate import process_real_estate_item\n'
      '                    property_type = proj_name[len("scout-realestate-"):]\n'
      '                    should_post, _re_analysis, re_strategy_note = process_real_estate_item(\n'
      '                        text=item.text, url=getattr(item, "url", "") or "",\n'
      '                        property_type=property_type, data_dir=self._data_dir,\n'
      '                    )\n'
      '                    if not should_post:\n'
      '                        report.filtered += 1\n'
      '                        continue\n'
      '                key = f"{source.name}:{item.id}"\n'
      '                if key in self._seen:\n'
      '                    continue\n'
      '                self._seen.add(key)\n'
      '                alert_content = _format_alert(self.project, source, item)\n'
      '                if re_strategy_note:\n'
      '                    alert_content = f"{alert_content}\\n\\n💡 {re_strategy_note}"\n'
      '                alert = Alert(source=source.name, item_id=item.id,\n'
      '                              content=alert_content,\n'
      '                              title=item.text,\n'
      '                              url=getattr(item, "url", "") or "",\n'
      '                              embed=getattr(item, "embed", None))\n',
      "runtime.py real-estate gate hook")

# ── tests/test_discord_admin.py (existing hardcoded counts need bumping:
#    +1 new category, +3 tracker subscribe roles for the 3 new verticals) ──
tda = pkg.parent.parent / "tests" / "test_discord_admin.py"
patch(tda, '"REAL ESTATE",         # real-estate-d',
      '                    "DOLLAR GENERAL",         # dollargeneral-d\n'
      '                    "LOUNGE", "PAYOUTS", "MEAD LOUNGE",',
      '                    "DOLLAR GENERAL",         # dollargeneral-d\n'
      '                    "REAL ESTATE",         # real-estate-d\n'
      '                    "LOUNGE", "PAYOUTS", "MEAD LOUNGE",',
      "test_discord_admin.py category list +REAL ESTATE")

patch(tda, 'create_role") == 72',
      'assert ops.count("create_role") == 69   # +Mead-Head, +33 tracker subscribe roles, +3 pass roles, +target, +4 warframe item-type roles, +6 bestbuy item-type roles, -1 old target role +6 target item-type roles, +4 samsclub/costco item-type roles, +1 dollargeneral item-type role, -1 old warframe-arcanes +3 arcane-rank roles +1 warframe-misc role, +1 warframe-jackpot role',
      'assert ops.count("create_role") == 72   # +Mead-Head, +33 tracker subscribe roles, +3 pass roles, +target, +4 warframe item-type roles, +6 bestbuy item-type roles, -1 old target role +6 target item-type roles, +4 samsclub/costco item-type roles, +1 dollargeneral item-type role, -1 old warframe-arcanes +3 arcane-rank roles +1 warframe-misc role, +1 warframe-jackpot role, +3 real-estate item-type roles',
      "test_discord_admin.py role count (ops.count) 69->72")

patch(tda, 'a.op == "create_role") == 72',
      'assert sum(1 for a in acts if a.op == "create_role") == 69   # +Mead-Head, +33 tracker subscribe roles, +3 pass roles, +target, +4 warframe item-type roles, +6 bestbuy item-type roles, -1 old target role +6 target item-type roles, +4 samsclub/costco item-type roles, +1 dollargeneral item-type role, -1 old warframe-arcanes +3 arcane-rank roles +1 warframe-misc role, +1 warframe-jackpot role',
      'assert sum(1 for a in acts if a.op == "create_role") == 72   # +Mead-Head, +33 tracker subscribe roles, +3 pass roles, +target, +4 warframe item-type roles, +6 bestbuy item-type roles, -1 old target role +6 target item-type roles, +4 samsclub/costco item-type roles, +1 dollargeneral item-type role, -1 old warframe-arcanes +3 arcane-rank roles +1 warframe-misc role, +1 warframe-jackpot role, +3 real-estate item-type roles',
      "test_discord_admin.py role count (sum generator) 69->72")

patch(tda, 'create_category") == 25',
      'assert ops.count("create_category") == 24  # +COMMAND (F5, 2026-07-19), +WARFRAME, +ADMIN, +BEST BUY, +TARGET, +SAM\'S CLUB, +COSTCO, +DOLLAR GENERAL',
      'assert ops.count("create_category") == 25  # +COMMAND (F5, 2026-07-19), +WARFRAME, +ADMIN, +BEST BUY, +TARGET, +SAM\'S CLUB, +COSTCO, +DOLLAR GENERAL, +REAL ESTATE',
      "test_discord_admin.py category count 24->25")

patch(tda, 'create_channel") == 105',
      'assert ops.count("create_channel") == 100   # +owner-bridge +staff-room +angel-voice, +buy-links +product-drops +setup, +target, +4 warframe item-type channels, +4 admin channels, +6 bestbuy item-type channels, -1 old track-target +6 target item-type channels, +4 samsclub/costco item-type channels, +1 dollargeneral item-type channel, -1 old arcanes +3 arcane-rank channels +1 misc channel, +1 item-lookup channel, +1 jackpot channel',
      'assert ops.count("create_channel") == 105   # +owner-bridge +staff-room +angel-voice, +buy-links +product-drops +setup, +target, +4 warframe item-type channels, +4 admin channels, +6 bestbuy item-type channels, -1 old track-target +6 target item-type channels, +4 samsclub/costco item-type channels, +1 dollargeneral item-type channel, -1 old arcanes +3 arcane-rank channels +1 misc channel, +1 item-lookup channel, +1 jackpot channel, +5 real-estate channels (single-family/condos/apartments/secure-deals/requirements)',
      "test_discord_admin.py create_channel count 100->105")

# ── discord_admin/bot.py ─────────────────────────────────────────────────
bt = pkg / "discord_admin" / "bot.py"
patch(bt, 'channel_name == "requirements"',
      '            if channel_name == "owner-bridge":\n',
      '            # real-estate-requirements-d (Kevin, 2026-07-29): "channel\n'
      '            # and what my requirements would be" — Kevin\'s own buy-box\n'
      '            # criteria, set via plain key=value text in #requirements.\n'
      '            # Owner-only, same defense-in-depth as owner-bridge/angel-voice.\n'
      '            if channel_name == "requirements":\n'
      '                if str(message.author.id) != ctx.owner_id:\n'
      '                    return\n'
      '                content = (message.content or "").strip()\n'
      '                if not content:\n'
      '                    return\n'
      '                from sovereign_agent import real_estate_requirements as _rereq\n'
      '\n'
      '                existing = _rereq.load_requirements(data_dir)\n'
      '                updated = _rereq.apply_command(existing, content)\n'
      '                _rereq.save_requirements(data_dir, updated)\n'
      '                await message.channel.send(_rereq.summarize(updated))\n'
      '                return\n'
      '            if channel_name == "owner-bridge":\n',
      "bot.py #requirements channel handler")

print("→ compile check")
import py_compile
for rel in ("verticals.py", "discord_admin/blueprint.py",
            "discord_runtime/runtime.py", "discord_admin/bot.py"):
    py_compile.compile(str(pkg / rel), doraise=True)
py_compile.compile(str(pkg.parent.parent / "tests" / "test_discord_admin.py"), doraise=True)
print("  ✓ all patched files compile")
PYEOF

echo "→ compile check on new modules"
python3 -m py_compile \
  "$PKG/real_estate_deal_analyzer.py" \
  "$PKG/real_estate_requirements.py" \
  "$PKG/real_estate_strategy.py" \
  "$PKG/real_estate_gate.py"
echo "  ✓ compiles"

echo "→ installing tests"
for f in test_real_estate_deal_analyzer.py test_real_estate_requirements.py \
         test_real_estate_strategy.py test_real_estate_gate.py; do
  cp "$HERE/tests/$f" "$ROOT/tests/$f"
  echo "  ✓ tests/$f"
done
python3 -m py_compile "$ROOT"/tests/test_real_estate_*.py
echo "  ✓ tests compile"

echo
echo "✓ done."
echo "  Next: run \`sov scout sync\` and confirm the REAL ESTATE category +"
echo "  its 5 channels (single-family, condos, apartments, secure-deals,"
echo "  requirements) appear in Discord."
echo "  Then set your buy-box in #requirements, e.g.:"
echo "    zips=90210 radius=20 price_max=300000 min_cash_flow=200 types=single-family,condo"
echo
echo "  Still open (v1 scope, by design — see this script's header):"
echo "  county/HUD/USDA open-data sources aren't wired in yet — tell Aria"
echo "  your target county's real open-data portal URL to add them."
echo
