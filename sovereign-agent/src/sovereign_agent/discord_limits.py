"""discord_limits.py — 📏 Discord's hard caps, named once, enforced once.

Kevin's ask (2026-07-17, right after the storefront silently dropped its
11th card): "What is Aria's character limit? Do we need to build a
structure around that so she never breaks it?" Yes — this module IS that
structure. Every documented cap lives here as a named constant, with
clamp/chunk helpers, and the delivery layer applies them at the one door
every webhook message leaves through. Scattered hand-caps ([:1900],
[:1500]) stay as belt-and-suspenders, but nothing depends on remembering
them anymore.

The caps (Discord API docs, stable for years):
  • message content: 2000 chars
  • embeds per message: 10
  • one embed: title 256 · description 4096 · footer 2048 · author 256 ·
    field name 256 · field value 1024 · 25 fields
  • ALL embeds in one message combined: 6000 chars
  • webhook username: 80
Breaking any of these = HTTP 400 and the message is LOST — a silent
customer-facing failure, which is why the clamp is structural.
"""
from __future__ import annotations

MSG_CONTENT_CHARS = 2000
EMBEDS_PER_MESSAGE = 10
EMBED_TITLE_CHARS = 256
EMBED_DESC_CHARS = 4096
EMBED_FOOTER_CHARS = 2048
EMBED_AUTHOR_CHARS = 256
EMBED_FIELD_NAME_CHARS = 256
EMBED_FIELD_VALUE_CHARS = 1024
EMBED_FIELDS_MAX = 25
EMBED_TOTAL_CHARS = 6000        # sum of every text part of every embed
WEBHOOK_USERNAME_CHARS = 80

_ELLIPSIS = "…"


def clamp_text(text: str, limit: int) -> str:
    """Hard-cap with a visible ellipsis — truncation should be seeable,
    never silent."""
    t = str(text or "")
    if len(t) <= limit:
        return t
    return t[: max(limit - 1, 0)] + _ELLIPSIS


def embed_chars(embed: dict) -> int:
    """The characters Discord counts toward the 6000/message embed cap."""
    n = len(str(embed.get("title", ""))) + len(str(embed.get("description", "")))
    n += len(str((embed.get("footer") or {}).get("text", "")))
    n += len(str((embed.get("author") or {}).get("name", "")))
    for f in embed.get("fields", []) or []:
        n += len(str(f.get("name", ""))) + len(str(f.get("value", "")))
    return n


def clamp_embed(embed: dict) -> dict:
    """Return a copy with every per-part cap enforced."""
    e = dict(embed or {})
    if "title" in e:
        e["title"] = clamp_text(e["title"], EMBED_TITLE_CHARS)
    if "description" in e:
        e["description"] = clamp_text(e["description"], EMBED_DESC_CHARS)
    if isinstance(e.get("footer"), dict) and "text" in e["footer"]:
        e["footer"] = {**e["footer"],
                       "text": clamp_text(e["footer"]["text"],
                                          EMBED_FOOTER_CHARS)}
    if isinstance(e.get("author"), dict) and "name" in e["author"]:
        e["author"] = {**e["author"],
                       "name": clamp_text(e["author"]["name"],
                                          EMBED_AUTHOR_CHARS)}
    if e.get("fields"):
        e["fields"] = [
            {**f, "name": clamp_text(f.get("name", ""), EMBED_FIELD_NAME_CHARS),
             "value": clamp_text(f.get("value", ""), EMBED_FIELD_VALUE_CHARS)}
            for f in list(e["fields"])[:EMBED_FIELDS_MAX]]
    return e


def chunk_embeds(embeds: list[dict],
                 per_message: int = EMBEDS_PER_MESSAGE,
                 total_chars: int = EMBED_TOTAL_CHARS) -> list[list[dict]]:
    """Split embeds into message-sized chunks honoring BOTH caps: at most
    `per_message` embeds AND at most `total_chars` combined characters per
    chunk. Every embed is clamped first, so a single embed always fits."""
    chunks: list[list[dict]] = []
    cur: list[dict] = []
    cur_chars = 0
    for raw in embeds or []:
        e = clamp_embed(raw)
        n = embed_chars(e)
        if cur and (len(cur) >= per_message or cur_chars + n > total_chars):
            chunks.append(cur)
            cur, cur_chars = [], 0
        cur.append(e)
        cur_chars += n
    if cur:
        chunks.append(cur)
    return chunks


def split_text(text: str, limit: int = MSG_CONTENT_CHARS) -> list[str]:
    """Kevin's 'be smart about it': long text becomes SEVERAL messages,
    split at natural seams — paragraph first, then line, then sentence,
    then word — so nothing a customer reads is ever chopped mid-thought.
    Only an unbroken >limit run of characters is hard-cut."""
    text = str(text or "").strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    out: list[str] = []
    rest = text
    while len(rest) > limit:
        window = rest[:limit]
        cut = -1
        for sep in ("\n\n", "\n", ". ", "! ", "? ", " "):
            cut = window.rfind(sep)
            if cut > limit // 4:          # a decent-sized first piece
                cut += len(sep.rstrip()) or 1
                break
            cut = -1
        if cut <= 0:
            cut = limit                   # unbroken run — hard cut, honest
        out.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        out.append(rest)
    return out


__all__ = ["MSG_CONTENT_CHARS", "EMBEDS_PER_MESSAGE", "EMBED_TITLE_CHARS",
           "EMBED_DESC_CHARS", "EMBED_FOOTER_CHARS", "EMBED_AUTHOR_CHARS",
           "EMBED_FIELD_NAME_CHARS", "EMBED_FIELD_VALUE_CHARS",
           "EMBED_FIELDS_MAX", "EMBED_TOTAL_CHARS", "WEBHOOK_USERNAME_CHARS",
           "clamp_text", "embed_chars", "clamp_embed", "chunk_embeds",
           "split_text"]
