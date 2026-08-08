#!/usr/bin/env python3
"""scan_listings.py — ground truth: what ACTUALLY landed in the Discord channels.

listings-scanner-d (Kevin, 2026-08-03): "Create a listings scanner that can
scan the channels for listings... maybe that is why it is not sending or it
gets rejected unnoticed."

The run logs only prove Discord returned 2xx to a webhook POST. They do NOT
prove a usable listing rendered in the channel. This reads the channels
themselves via the bot's gateway connection and reports, per channel:

  • how many messages are actually there, and how old the newest is
  • how many parse as a real listing (address / case / sale date / amount)
  • how many carry a clickable link  ← Kevin's hypothesis
  • how many are bare/empty/placeholder posts that a human can't act on

Read-only. Never posts, never edits, never deletes.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys

# what makes a post actionable to a human looking for a deal
_LINK_RE = re.compile(r"https?://[^\s<>()\]]+")
_ADDRESS_RE = re.compile(
    r"\d+\s+[A-Za-z0-9.'-]+(?:\s+[A-Za-z0-9.'-]+){0,4}\s+"
    r"(?:st|street|rd|road|ave|avenue|dr|drive|ln|lane|ct|court|"
    r"blvd|boulevard|way|pl|place|cir|circle|hwy|highway|pike|trail|tr)\b",
    re.IGNORECASE)
_CITY_STATE_RE = re.compile(r"\b[A-Z][a-zA-Z .'-]+,\s*[A-Z]{2}\b")
_CASE_RE = re.compile(r"\b\d{2}-[A-Z]{2}-\d{3,6}\b")
_MONEY_RE = re.compile(r"\$\s?[\d,]+(?:\.\d{2})?")
_SALE_DATE_RE = re.compile(r"sale\s*date", re.IGNORECASE)


def _text_of(msg) -> str:
    """Everything a human would actually see — content AND embed fields.
    A webhook post with an empty `content` but a full embed is a REAL
    listing; counting only `content` would report a false failure."""
    parts = [msg.content or ""]
    for e in getattr(msg, "embeds", None) or []:
        for attr in ("title", "description", "url"):
            v = getattr(e, attr, None)
            if v:
                parts.append(str(v))
        for f in getattr(e, "fields", None) or []:
            parts.append(f"{getattr(f, 'name', '')} {getattr(f, 'value', '')}")
        foot = getattr(e, "footer", None)
        if foot is not None and getattr(foot, "text", None):
            parts.append(str(foot.text))
    return "\n".join(p for p in parts if p)


def classify(text: str) -> dict:
    """What signals does this post actually carry?"""
    return {
        "link": bool(_LINK_RE.search(text)),
        "address": bool(_ADDRESS_RE.search(text)),
        "city_state": bool(_CITY_STATE_RE.search(text)),
        "case": bool(_CASE_RE.search(text)),
        "money": bool(_MONEY_RE.search(text)),
        "sale_date": bool(_SALE_DATE_RE.search(text)),
    }


def is_listing(sig: dict) -> bool:
    """A real listing names a PLACE plus at least one hard detail."""
    located = sig["address"] or sig["city_state"]
    detailed = sig["case"] or sig["money"] or sig["sale_date"]
    return located and detailed


async def scan(channel_filter: str, limit: int, guild_id: str | None) -> int:
    try:
        import discord
    except ImportError:
        print("ERROR: discord.py not installed in this venv", file=sys.stderr)
        return 2

    from sovereign_agent.credentials import read_env
    env = read_env()
    token = (env.get("DISCORD_BOT_TOKEN") or "").strip()
    guild_id = guild_id or (env.get("DISCORD_GUILD_ID") or "").strip()
    if not token:
        print("ERROR: no DISCORD_BOT_TOKEN in the vault", file=sys.stderr)
        return 2

    # message_content is a PRIVILEGED intent. Without it Discord returns
    # empty content/embeds for posts this bot didn't author — which would
    # look identical to "the channel is full of blank junk" and produce a
    # totally false diagnosis. So: try WITH it, and if the portal hasn't
    # granted it, fall back to a metadata-only scan that reports counts and
    # ages honestly and says plainly that content analysis is unavailable.
    can_read_content = {"ok": True}
    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)
    rc = {"code": 1}

    @client.event
    async def on_ready():  # noqa: ANN202
        try:
            guild = (client.get_guild(int(guild_id)) if guild_id
                     else (client.guilds[0] if client.guilds else None))
            if guild is None:
                print("ERROR: bot is in no guild / guild id not found",
                      file=sys.stderr)
                rc["code"] = 2
                return

            chans = [c for c in guild.text_channels
                     if channel_filter.lower() in c.name.lower()]
            if not chans:
                print(f"No channels matching '{channel_filter}' in {guild.name}.")
                names = ", ".join(sorted(c.name for c in guild.text_channels)[:40])
                print(f"Available: {names}")
                rc["code"] = 1
                return

            print(f"Scanning {len(chans)} channel(s) in {guild.name}\n")
            grand = {"msgs": 0, "listings": 0, "linked": 0, "unusable": 0}

            for ch in sorted(chans, key=lambda c: c.name):
                try:
                    msgs = [m async for m in ch.history(limit=limit)]
                except discord.Forbidden:
                    print(f"  #{ch.name:28} — NO READ ACCESS (bot lacks "
                          f"Read Message History)")
                    continue
                except Exception as exc:  # noqa: BLE001
                    print(f"  #{ch.name:28} — ERROR {type(exc).__name__}")
                    continue

                listings = linked = unusable = 0
                newest = None
                for m in msgs:
                    if newest is None:
                        newest = m.created_at
                    if not can_read_content["ok"]:
                        continue          # counts + ages only; see note below
                    txt = _text_of(m)
                    if not txt.strip():
                        unusable += 1
                        continue
                    sig = classify(txt)
                    if is_listing(sig):
                        listings += 1
                        if sig["link"]:
                            linked += 1
                    elif not sig["link"]:
                        unusable += 1

                grand["msgs"] += len(msgs)
                grand["listings"] += listings
                grand["linked"] += linked
                grand["unusable"] += unusable

                age = "EMPTY — nothing ever posted"
                if newest is not None:
                    import datetime as _dt
                    hrs = (_dt.datetime.now(_dt.timezone.utc)
                           - newest).total_seconds() / 3600
                    age = f"newest {hrs:.0f}h ago"
                if not can_read_content["ok"]:
                    print(f"  #{ch.name:28} {len(msgs):4d} msgs · {age}")
                    continue
                nolink = listings - linked
                flag = "  ⚠ listings WITHOUT a link" if nolink else ""
                print(f"  #{ch.name:28} {len(msgs):4d} msgs · "
                      f"{listings:3d} listings · {linked:3d} w/ link · "
                      f"{nolink:3d} w/o link · {age}{flag}")

            if not can_read_content["ok"]:
                print(f"\nTOTAL  {grand['msgs']} messages across "
                      f"{len(chans)} channel(s)")
                print("\nNOTE: message-content analysis UNAVAILABLE — the "
                      "'Message Content Intent' is not enabled for this bot.\n"
                      "      Counts and ages above are real; listing/link "
                      "breakdown needs that intent.\n"
                      "      Enable at https://discord.com/developers/applications"
                      " → your app → Bot → Message Content Intent, then re-run.")
            else:
                print(f"\nTOTAL  {grand['msgs']} messages · "
                      f"{grand['listings']} listings · {grand['linked']} with a link "
                      f"· {grand['listings'] - grand['linked']} without · "
                      f"{grand['unusable']} unusable/empty")
            rc["code"] = 0
        finally:
            await client.close()

    try:
        await client.start(token)
    except discord.errors.PrivilegedIntentsRequired:
        # Not granted in the portal — redo the whole scan metadata-only
        # rather than reporting a false "all posts are blank".
        can_read_content["ok"] = False
        intents2 = discord.Intents.default()
        intents2.message_content = False
        client2 = discord.Client(intents=intents2)
        client2.on_ready = on_ready          # same scan body, degraded mode
        client = client2
        await client2.start(token)
    return rc["code"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("channel_filter", nargs="?", default="county",
                    help="substring of channel names to scan "
                         "(default: 'county')")
    ap.add_argument("--limit", type=int, default=200,
                    help="messages per channel (default 200)")
    ap.add_argument("--guild", default=None, help="guild id override")
    a = ap.parse_args()
    return asyncio.run(scan(a.channel_filter, a.limit, a.guild))


if __name__ == "__main__":
    raise SystemExit(main())
