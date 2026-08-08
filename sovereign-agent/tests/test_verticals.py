"""Tests for verticals.py — the money map catalog."""
from __future__ import annotations

from sovereign_agent.verticals import (
    CATALOG,
    CATALOG_BY_SLUG,
    DEEP,
    STAR,
    deep_verticals,
    get_vertical,
    reddit_search,
    reddit_sub,
    slickdeals,
    star_verticals,
)


def test_catalog_integrity():
    assert len(CATALOG) >= 30                     # Kevin: dozens
    slugs = [v.slug for v in CATALOG]
    assert len(slugs) == len(set(slugs)), "duplicate vertical slugs"
    for v in CATALOG:
        assert v.sources, f"{v.slug} has no sources"
        assert v.tier in (STAR, DEEP)
        assert v.lane in ("deals", "online", "local")
        assert v.project == f"scout-{v.slug}"
        assert v.track_channel and v.ping_role
        assert v.price_cents > 0 and v.blurb
        # every source is a real (name, url, kind) triple — warframe-flip
        # is the one exception: its url is unused (WarframeFlipFetcher
        # drives its own internal multi-item rotation instead).
        for name, url, kind in v.sources:
            assert name
            if kind != "warframe-flip":
                assert url.startswith("http")
            assert kind in ("rss", "scrape", "warframe-flip", "grants-gov")


def test_priority_split():
    stars = star_verticals()
    assert 5 <= len(stars) <= 15                  # front-row stays clean
    assert all(v.tier == STAR for v in stars)
    assert len(deep_verticals()) >= 15            # the "view more" depth
    slugs = {v.slug for v in stars}
    for must in ("pokemon", "sneakers", "lego", "gpus"):
        assert must in slugs, f"{must} should be a priority tracker"


def test_source_builders():
    n, u, k = slickdeals("nike jordan")
    assert n.startswith("sd-") and "q=nike" in u and "rss=1" in u and k == "rss"
    n, u, k = reddit_sub("sneakers")
    assert n == "r-sneakers" and u.endswith("/r/sneakers/new/.rss") and k == "rss"
    n, u, k = reddit_search("lego", "retiring")
    assert "search.rss" in u and "restrict_sr=1" in u and k == "rss"


def test_scrape_source_builder():
    from sovereign_agent.verticals import scrape
    n, u, k = scrape("target-gpu-search", "https://www.target.com/s?searchTerm=gpu")
    assert n == "target-gpu-search"
    assert u == "https://www.target.com/s?searchTerm=gpu"
    assert k == "scrape"


def test_lookup():
    assert get_vertical("sneakers").name == "Sneakers"
    assert get_vertical("nope") is None
    assert CATALOG_BY_SLUG["lego"].emoji == "🧱"


def test_category_sets_integrity():
    """categories-d: every named category resolves fully — real slugs,
    explicit clean channels, no channel claimed twice anywhere."""
    from sovereign_agent.verticals import (
        CATEGORY_SLUGS, category_verticals, channeled_verticals, homed_slugs)
    for cat, slugs in CATEGORY_SLUGS.items():
        assert slugs, f"{cat} is empty"
        vs = category_verticals(cat)
        assert len(vs) == len(slugs), f"{cat} has unknown slugs"
        for v in vs:
            # homed verticals own a CLEAN channel name, never track-<slug>
            assert v.channel, f"{v.slug} in {cat} needs an explicit channel"
    # Kevin's exact channel layout, in his order
    assert [v.track_channel for v in category_verticals("COMPUTERS")] == [
        "desktops", "servers", "laptops", "phones", "desktop-parts",
        "server-parts", "laptop-parts", "phone-parts"]
    assert [v.track_channel for v in category_verticals("CLOTHING")] == [
        "mens-clothes", "womens-clothes", "childrens-clothes",
        "childrens-toys", "accessories"]
    assert [v.track_channel for v in category_verticals("PETS")] == [
        "pet-food", "pet-toys", "pet-accessories"]
    assert [v.track_channel for v in category_verticals("VEHICLES")] == [
        "vehicles", "vehicle-parts"]
    assert [v.track_channel for v in category_verticals("WHOLESALE")] == [
        "wholesale-lots", "liquidation"]
    # the one canonical list: deduped, and channel names never collide
    chans = [v.track_channel for v in channeled_verticals()]
    assert len(chans) == len(set(chans)), "duplicate tracker channels"
    assert "gpus" in homed_slugs()          # the star lives in COMPUTERS now


def test_expansion_is_slickdeals_first():
    """Kevin: 'the Reddit rate limit is too soft — we need other API
    sources.' Every new-category vertical leads with Slickdeals; reddit
    is garnish (never the majority of its sources)."""
    from sovereign_agent.verticals import CATEGORY_SLUGS, get_vertical
    new_cats = ("COMPUTERS", "VEHICLES", "CLOTHING", "PETS", "WHOLESALE")
    for cat in new_cats:
        for slug in CATEGORY_SLUGS[cat]:
            v = get_vertical(slug)
            reddit = [u for _, u, _ in v.sources if "reddit.com" in u]
            assert len(reddit) * 2 <= len(v.sources), \
                f"{slug}: reddit-heavy ({len(reddit)}/{len(v.sources)})"
            assert any("slickdeals.net" in u for _, u, _ in v.sources), \
                f"{slug}: no Slickdeals lane"


def test_tracker_products_seed_and_valid(tmp_path):
    """V4: each ★ vertical → a sellable product + one all-access Scout Pass,
    all name-valid (accents/em-dash/! folded)."""
    from sovereign_agent.shop import (
        list_all, seed_tracker_products, validate)
    written = seed_tracker_products(tmp_path)
    from sovereign_agent.verticals import star_verticals
    assert len(written) == len(star_verticals()) + 1     # +Scout Pass
    for p in written:
        assert validate(p) == [], f"{p.name}: {validate(p)}"
    names = {p.name for p in list_all(tmp_path)}
    assert "Scout Pass All-Access" in names
    assert any("Sneakers" in n for n in names)
    # idempotent
    assert seed_tracker_products(tmp_path) == []


# ── tracker-toggle-d: owner on/off per vertical ──────────────────────────
# Kevin, 2026-07-25: "a way for me to turn channels on and maybe turn
# some channels off?"

def _sync_one(tmp_path, slug):
    """Mimic exactly what `sov scout sync` does for one vertical: create
    its BotProject record so the toggle has something real to flip."""
    from sovereign_agent import bot_projects
    v = CATALOG_BY_SLUG[slug]
    p = bot_projects.BotProject(project_name=v.project, bot_name=v.name,
                                 kind="restock-alert", status="building",
                                 description=v.blurb)
    bot_projects.save(p, tmp_path)
    return p


def test_set_tracker_enabled_unknown_slug(tmp_path):
    from sovereign_agent.verticals import set_tracker_enabled
    ok, msg = set_tracker_enabled(tmp_path, "not-a-real-slug", True)
    assert ok is False
    assert "no tracker vertical" in msg


def test_set_tracker_enabled_before_sync(tmp_path):
    """The vertical is real but hasn't been synced into a BotProject yet."""
    from sovereign_agent.verticals import set_tracker_enabled
    ok, msg = set_tracker_enabled(tmp_path, "lego", False)
    assert ok is False
    assert "sov scout sync" in msg


def test_set_tracker_enabled_pauses_and_resumes(tmp_path):
    from sovereign_agent import bot_projects
    from sovereign_agent.verticals import set_tracker_enabled
    _sync_one(tmp_path, "lego")

    ok, msg = set_tracker_enabled(tmp_path, "lego", False)
    assert ok is True
    assert "paused" in msg
    p = bot_projects.load("scout-lego", tmp_path)
    assert p.status == "paused"

    ok, msg = set_tracker_enabled(tmp_path, "lego", True)
    assert ok is True
    assert "resumed" in msg
    p = bot_projects.load("scout-lego", tmp_path)
    assert p.status == "live"


def test_set_tracker_enabled_paused_project_is_skipped_by_the_fleet(tmp_path):
    """The real point: pausing here must actually silence delivery —
    confirm it round-trips through BotManager.load()'s live skip-list."""
    from sovereign_agent.discord_runtime.manager import BotManager
    from sovereign_agent.verticals import set_tracker_enabled
    _sync_one(tmp_path, "lego")
    set_tracker_enabled(tmp_path, "lego", False)

    mgr = BotManager(tmp_path, live=False)
    loaded = mgr.load()
    assert "scout-lego" not in {p.project_name for p in loaded}
    assert "scout-lego" not in mgr._runtimes


# ── my-panel-d: category grouping for the per-user subscribe panel ───────
# Kevin, 2026-07-26: "a per user control panel... buttons to subscribe to
# each category... categories and channels... quick select categories
# then the channels can be selected or deselected."

def test_subscribable_categories_matches_the_declared_order():
    from sovereign_agent.verticals import SUBSCRIBABLE_CATEGORIES, subscribable_categories
    assert list(subscribable_categories().keys()) == list(SUBSCRIBABLE_CATEGORIES)


def test_subscribable_categories_covers_every_channeled_vertical_exactly_once():
    from sovereign_agent.verticals import channeled_verticals, subscribable_categories
    cats = subscribable_categories()
    grouped = [v.slug for verts in cats.values() for v in verts]
    assert sorted(grouped) == sorted(v.slug for v in channeled_verticals())
    assert len(grouped) == len(set(grouped))  # no vertical double-counted


def test_trackers_bucket_excludes_homed_verticals():
    from sovereign_agent.verticals import homed_slugs, subscribable_categories
    homed = homed_slugs()
    trackers = subscribable_categories()["TRACKERS"]
    assert not any(v.slug in homed for v in trackers)


def test_gaming_bucket_matches_category_verticals():
    from sovereign_agent.verticals import category_verticals, subscribable_categories
    assert subscribable_categories()["GAMING"] == category_verticals("GAMING")


# ── my-panel-d: bulk-toggle + select-diff decision logic (pure) ──────────

def test_bulk_toggle_subscribes_to_everything_missing_when_none_held():
    from sovereign_agent.verticals import bulk_toggle_roles, category_verticals
    verts = category_verticals("PETS")
    action, roles = bulk_toggle_roles(verts, set())
    assert action == "subscribe"
    assert set(roles) == {v.ping_role for v in verts}


def test_bulk_toggle_unsubscribes_from_everything_when_all_held():
    from sovereign_agent.verticals import bulk_toggle_roles, category_verticals
    verts = category_verticals("PETS")
    all_roles = {v.ping_role for v in verts}
    action, roles = bulk_toggle_roles(verts, all_roles)
    assert action == "unsubscribe"
    assert set(roles) == all_roles


def test_bulk_toggle_subscribes_to_only_the_missing_ones_when_partial():
    from sovereign_agent.verticals import bulk_toggle_roles, category_verticals
    verts = category_verticals("PETS")
    have_first_only = {verts[0].ping_role}
    action, roles = bulk_toggle_roles(verts, have_first_only)
    assert action == "subscribe"
    assert verts[0].ping_role not in roles
    assert all(v.ping_role in roles for v in verts[1:])


def test_bulk_toggle_empty_category_is_a_safe_no_op():
    from sovereign_agent.verticals import bulk_toggle_roles
    action, roles = bulk_toggle_roles([], set())
    assert action == "subscribe"
    assert roles == []


def test_select_diff_adds_newly_checked_and_removes_unchecked():
    from sovereign_agent.verticals import category_verticals, select_diff_roles
    verts = category_verticals("PETS")
    # currently subscribed to verts[0] only; member just checked verts[1] and
    # verts[2] in the dropdown but left verts[0] unchecked
    have = {verts[0].ping_role}
    selected = {verts[1].slug, verts[2].slug}
    add, remove = select_diff_roles(verts, have, selected)
    assert set(add) == {verts[1].ping_role, verts[2].ping_role}
    assert remove == [verts[0].ping_role]


def test_select_diff_is_idempotent_when_selection_matches_current_state():
    from sovereign_agent.verticals import category_verticals, select_diff_roles
    verts = category_verticals("PETS")
    have = {verts[0].ping_role, verts[1].ping_role}
    selected = {verts[0].slug, verts[1].slug}
    add, remove = select_diff_roles(verts, have, selected)
    assert add == [] and remove == []


def test_select_diff_deselecting_everything_removes_all_held_roles():
    from sovereign_agent.verticals import category_verticals, select_diff_roles
    verts = category_verticals("PETS")
    have = {v.ping_role for v in verts}
    add, remove = select_diff_roles(verts, have, selected_slugs=())
    assert add == []
    assert set(remove) == have
