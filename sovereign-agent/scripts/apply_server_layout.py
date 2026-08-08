#!/usr/bin/env python3
"""apply_server_layout.py — make the live Discord server match the blueprint.

Does the three things the bot's own commands can't do together, in the only
order that works:

  1. RE-HOME  channels stranded in a retired category (#owner-bridge etc.
     still sitting in COMMAND after it was folded into ADMIN). Must run
     first — a channel that changes category gets a fresh position.
  2. REORDER  categories into blueprint order.
  3. PRUNE    categories the blueprint no longer has, once they're empty.

Safety:
  • --apply is required. Without it this is a dry run that touches nothing.
  • Only deletes a category that is EMPTY and absent from the blueprint. It
    never deletes a channel — if something unexpected is still inside, the
    category survives and is reported, because a surprise here would be
    someone's data.
  • Channels the blueprint doesn't know are never moved or adopted.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

import discord

from sovereign_agent.credentials import read_env
from sovereign_agent.discord_admin.blueprint import canon_name, shop_blueprint
from sovereign_agent.discord_admin.reorder import plan_positions, plan_rehome

PACE = 0.6          # be polite to the rate limiter


async def run(apply: bool) -> int:
    env = read_env()
    token = env["DISCORD_BOT_TOKEN"].strip()
    gid = int(env["DISCORD_GUILD_ID"].strip())
    client = discord.Client(intents=discord.Intents.default())
    rc = {"code": 1}

    @client.event
    async def on_ready():  # noqa: ANN202
        try:
            g = client.get_guild(gid)
            if g is None:
                print("ERROR: guild not found", file=sys.stderr)
                return
            bp = shop_blueprint()
            bp_cat_names = [c.name for c in bp.categories]
            bp_cats = {canon_name(n) for n in bp_cat_names}
            mode = "APPLY" if apply else "DRY RUN"
            print(f"=== {g.name} — {mode} ===\n")

            # ── 1. re-home ────────────────────────────────────────────
            bp_homes = {ch.name: c.name for c in bp.categories
                        for ch in c.channels}
            live_homes = {ch.name: (ch.category.name if ch.category else "")
                          for ch in g.text_channels}
            rehome = plan_rehome(bp_homes, live_homes)
            print(f"1. RE-HOME — {len(rehome)} channel(s)")
            cat_by_canon = {canon_name(c.name): c for c in g.categories}
            for name, want in rehome:
                target = cat_by_canon.get(canon_name(want))
                ch = discord.utils.get(g.text_channels, name=name)
                where = ch.category.name if ch and ch.category else "—"
                print(f"     #{name:22} {where} → {want}")
                if apply and ch is not None and target is not None:
                    await ch.edit(category=target, reason="apply_server_layout")
                    await asyncio.sleep(PACE)

            # ── 2. reorder categories ─────────────────────────────────
            live_cats = sorted(g.categories, key=lambda c: c.position)
            moves = plan_positions(bp_cat_names, [c.name for c in live_cats])
            print(f"\n2. REORDER — {len(moves)} category move(s)")
            for name, pos in moves:
                print(f"     {name:26} → position {pos}")
                if apply:
                    cat = discord.utils.get(g.categories, name=name)
                    if cat is not None:
                        await cat.edit(position=pos,
                                       reason="apply_server_layout")
                        await asyncio.sleep(PACE)

            # ── 3. prune empty retired categories ─────────────────────
            if apply:
                g = client.get_guild(gid)          # refresh after the moves
            stale = [c for c in g.categories if canon_name(c.name) not in bp_cats]
            print(f"\n3. PRUNE — {len(stale)} category(ies) not in the blueprint")
            for cat in stale:
                if cat.channels:
                    print(f"     {cat.name:26} KEPT — still holds "
                          f"{[c.name for c in cat.channels]}")
                    continue
                print(f"     {cat.name:26} {'deleting' if apply else 'would delete'} (empty)")
                if apply:
                    await cat.delete(reason="apply_server_layout: retired + empty")
                    await asyncio.sleep(PACE)

            if not apply:
                print("\nDry run — nothing changed. Re-run with --apply.")
            rc["code"] = 0
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
            rc["code"] = 2
        finally:
            await client.close()

    await client.start(token)
    return rc["code"]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="actually make the changes (default: dry run)")
    raise SystemExit(asyncio.run(run(ap.parse_args().apply)))
