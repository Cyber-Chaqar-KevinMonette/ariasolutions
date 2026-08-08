#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_reaction_roles.sh — reaction-roles: react to an emoji, get/lose a role
#
#  Kevin (2026-08-03): first real feature toward a standing, invite-able
#  Discord bot (the income-plan gateway-bot track) — reaction-roles needs zero
#  privileged Discord intents (guild_reactions is already in
#  discord.Intents.default()), so there's no verification bottleneck between
#  building it and eventually listing the bot publicly. v1 proves it on
#  Kevin's own server; storage is genuinely per-guild-scoped from day one so a
#  later multi-server phase is a distribution problem, not a rewrite.
#
#  Delivers:
#    - reaction_roles/ (new top-level package) — pure logic: per-guild
#      bindings store, emoji_key(), decide_reaction_role_action() (dry-run by
#      default), build_audit_entry(). No discord.py dependency.
#    - discord_admin/bot.py patches (anchor-based, NEVER a whole-file copy —
#      this file is large and live; a prior module in this repo had a near-
#      miss from a blind whole-file apply overwriting newer live code):
#        * 3 new COMMANDS catalog entries
#        * 3 new /reaction-role-* slash commands (team-gated via _is_staff),
#          inserted beside subscribe_cmd/unsubscribe_cmd (closest structural
#          sibling: staff-gated role mutation)
#        * on_raw_reaction_add/on_raw_reaction_remove handlers + the shared
#          _reaction_role_apply helper, inserted beside on_member_join (same
#          never-crash-the-gateway, always-audit-log discipline)
#    - Live grants gated behind DISCORD_ENABLE_REACTION_ROLE_GRANTS=1
#      (default: dry-run, logs "would grant/revoke", touches nothing).
#
#  Idempotent. Backs up bot.py before patching.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# root-detect-safety-d: an explicit $1 without the marker file must be
# trusted-or-refused, never silently overridden by an upward search that
# could resolve into the wrong repo (see aria-game-bridge/apply_game_bridge.sh
# for the incident this pattern fixes).
if [[ -n "${1:-}" ]]; then
  ROOT="$1"
  [[ -f "$ROOT/src/sovereign_agent/cli.py" ]] || {
    echo "✗ given root $ROOT has no src/sovereign_agent/cli.py — refusing to guess elsewhere"
    exit 1
  }
else
  ROOT="$PWD"
  if [[ ! -f "$ROOT/src/sovereign_agent/cli.py" ]]; then
    d="$PWD"
    while [[ "$d" != "/" ]]; do
      [[ -f "$d/src/sovereign_agent/cli.py" ]] && { ROOT="$d"; break; }
      d="$(dirname "$d")"
    done
  fi
  [[ -f "$ROOT/src/sovereign_agent/cli.py" ]] || { echo "✗ run from repo root"; exit 1; }
fi
echo "◊ repo root: $ROOT"

PKG="$ROOT/src/sovereign_agent"
ts(){ date +%Y%m%d%H%M%S; }

echo "→ installing reaction_roles/ (new top-level package)"
mkdir -p "$PKG/reaction_roles"
cp "$HERE"/payload/src/sovereign_agent/reaction_roles/*.py "$PKG/reaction_roles/"
echo "  ✓ reaction_roles/"

BOT="$PKG/discord_admin/bot.py"
echo "→ backing up discord_admin/bot.py"
cp "$BOT" "$BOT.bak.$(ts)"

python3 - "$BOT" <<'PYEOF'
import sys, pathlib

bot_path = pathlib.Path(sys.argv[1])


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


# ── 1. COMMANDS catalog — 3 new entries before the closing bracket ──────────
patch(
    bot_path,
    '("/reaction-role-add"',
    '    ("/create-role", "Create a role with an optional color.", "owner"),\n]',
    '    ("/create-role", "Create a role with an optional color.", "owner"),\n'
    '    ("/reaction-role-add", "🎭 Bind an emoji on a message to a role.", "team"),\n'
    '    ("/reaction-role-remove", "🎭 Remove a reaction-role binding.", "team"),\n'
    '    ("/reaction-role-list", "🎭 List reaction-role bindings.", "team"),\n]',
    "COMMANDS catalog entries",
)

# ── 2. slash commands — beside subscribe_cmd/unsubscribe_cmd ────────────────
old_cmds = (
    '            await member.remove_roles(role, reason="tracker unsubscribe")\n'
    '            await interaction.response.send_message(\n'
    '                f"🔕 unsubscribed from {v.emoji} {v.name} — "\n'
    '                f"#{v.track_channel} is hidden again.", ephemeral=True)\n'
    '\n'
    '        @tree.command(name="my-panel",'
)
new_cmds = (
    '            await member.remove_roles(role, reason="tracker unsubscribe")\n'
    '            await interaction.response.send_message(\n'
    '                f"🔕 unsubscribed from {v.emoji} {v.name} — "\n'
    '                f"#{v.track_channel} is hidden again.", ephemeral=True)\n'
    '\n'
    '        @tree.command(name="reaction-role-add", description="🎭 Bind an emoji on a message to a role.")\n'
    '        @discord.app_commands.describe(message_id="the message id to watch", channel="the channel the message is in",\n'
    '                                        emoji="the emoji to react with", role="the role to grant")\n'
    '        async def reaction_role_add_cmd(interaction, message_id: str, channel: discord.TextChannel,\n'
    '                                         emoji: str, role: discord.Role):\n'
    '            _remember(interaction.user)\n'
    '            if not _is_staff(interaction):\n'
    '                await interaction.response.send_message("team only.", ephemeral=True)\n'
    '                return\n'
    '            from sovereign_agent import reaction_roles as _rr\n'
    '            try:\n'
    '                message = await channel.fetch_message(int(message_id))\n'
    '            except Exception:  # noqa: BLE001\n'
    '                await interaction.response.send_message(\n'
    '                    f"couldn\'t find message {message_id} in {channel.mention}.", ephemeral=True)\n'
    '                return\n'
    '            try:\n'
    '                await message.add_reaction(emoji)\n'
    '            except Exception:  # noqa: BLE001\n'
    '                pass\n'
    '            key = _rr.emoji_key(getattr(emoji, "id", None), str(emoji))\n'
    '            entry = _rr.add_binding(\n'
    '                data_dir, str(interaction.guild.id), message_id=str(message.id),\n'
    '                channel_id=str(channel.id), emoji_key=key, emoji_display=str(emoji),\n'
    '                role_id=str(role.id), created_by=str(interaction.user.id))\n'
    '            audit_log(ctx.audit_path, {"op": "reaction_role_bind", "action": "add",\n'
    '                                       "guild_id": str(interaction.guild.id),\n'
    '                                       "binding_id": entry["binding_id"]})\n'
    '            await interaction.response.send_message(\n'
    '                f"🎭 bound {emoji} on that message → {role.mention}.", ephemeral=True)\n'
    '\n'
    '        @tree.command(name="reaction-role-remove", description="🎭 Remove a reaction-role binding.")\n'
    '        @discord.app_commands.describe(message_id="the message id", emoji="the bound emoji")\n'
    '        async def reaction_role_remove_cmd(interaction, message_id: str, emoji: str):\n'
    '            _remember(interaction.user)\n'
    '            if not _is_staff(interaction):\n'
    '                await interaction.response.send_message("team only.", ephemeral=True)\n'
    '                return\n'
    '            from sovereign_agent import reaction_roles as _rr\n'
    '            guild_id = str(interaction.guild.id)\n'
    '            key = _rr.emoji_key(getattr(emoji, "id", None), str(emoji))\n'
    '            binding = _rr.find_binding(data_dir, guild_id, message_id, key)\n'
    '            if binding is None:\n'
    '                await interaction.response.send_message("no matching binding found.", ephemeral=True)\n'
    '                return\n'
    '            _rr.remove_binding(data_dir, guild_id, binding["binding_id"])\n'
    '            audit_log(ctx.audit_path, {"op": "reaction_role_bind", "action": "remove",\n'
    '                                       "guild_id": guild_id, "binding_id": binding["binding_id"]})\n'
    '            await interaction.response.send_message("🎭 binding removed.", ephemeral=True)\n'
    '\n'
    '        @tree.command(name="reaction-role-list", description="🎭 List reaction-role bindings.")\n'
    '        async def reaction_role_list_cmd(interaction):\n'
    '            _remember(interaction.user)\n'
    '            if not _is_staff(interaction):\n'
    '                await interaction.response.send_message("team only.", ephemeral=True)\n'
    '                return\n'
    '            from sovereign_agent import reaction_roles as _rr\n'
    '            bindings = _rr.list_bindings(data_dir, str(interaction.guild.id))\n'
    '            if not bindings:\n'
    '                await interaction.response.send_message("no reaction-role bindings yet.", ephemeral=True)\n'
    '                return\n'
    '            lines = [f"• msg {b[\'message_id\']} — {b[\'emoji_display\']} → role {b[\'role_id\']}"\n'
    '                     for b in bindings[:25]]\n'
    '            await interaction.response.send_message("🎭 bindings:\\n" + "\\n".join(lines), ephemeral=True)\n'
    '\n'
    '        @tree.command(name="my-panel",'
)
patch(bot_path, 'name="reaction-role-add"', old_cmds, new_cmds, "reaction-role slash commands")

# ── 3. gateway handlers — beside on_member_join ──────────────────────────────
old_handlers = (
    '            audit_log(ctx.audit_path, {"op": "welcome", "user": str(member.id),\n'
    '                                       "applied": True})\n'
    '        except Exception:  # noqa: BLE001 — greeting must never crash the gateway\n'
    '            pass\n'
    '\n'
    '    async def _mail_drain_once() -> None:'
)
new_handlers = (
    '            audit_log(ctx.audit_path, {"op": "welcome", "user": str(member.id),\n'
    '                                       "applied": True})\n'
    '        except Exception:  # noqa: BLE001 — greeting must never crash the gateway\n'
    '            pass\n'
    '\n'
    '    async def _reaction_role_apply(payload, event_type: str) -> None:\n'
    '        """React to an emoji on a bound message -> grant/revoke a role.\n'
    '        Dry-run by default (DISCORD_ENABLE_REACTION_ROLE_GRANTS=1 to arm);\n'
    '        never crashes the gateway; always audit-logged."""\n'
    '        try:\n'
    '            if payload.user_id == client.user.id:\n'
    '                return                            # ignore our own pre-seeded reaction\n'
    '            from sovereign_agent import reaction_roles as _rr\n'
    '            guild_id = str(payload.guild_id or "")\n'
    '            if not guild_id or guild_id == "None":\n'
    '                return\n'
    '            emoji = payload.emoji\n'
    '            key = _rr.emoji_key(getattr(emoji, "id", None), str(emoji))\n'
    '            binding = _rr.find_binding(data_dir, guild_id, str(payload.message_id), key)\n'
    '            live = (_os.environ.get("DISCORD_ENABLE_REACTION_ROLE_GRANTS") or "") == "1"\n'
    '            decision = _rr.decide_reaction_role_action(binding, event_type, live=live)\n'
    '            entry = _rr.build_audit_entry(\n'
    '                decision, guild_id, str(payload.user_id),\n'
    '                str(payload.message_id), (binding or {}).get("role_id", ""))\n'
    '            if decision.action != "none" and live:\n'
    '                guild = client.get_guild(int(guild_id))\n'
    '                member = guild.get_member(int(payload.user_id)) if guild else None\n'
    '                if guild is not None and member is None:\n'
    '                    try:\n'
    '                        member = await guild.fetch_member(int(payload.user_id))\n'
    '                    except Exception:  # noqa: BLE001\n'
    '                        member = None\n'
    '                role = guild.get_role(int(binding["role_id"])) if guild else None\n'
    '                if role is not None and member is not None:\n'
    '                    try:\n'
    '                        if decision.action == "grant":\n'
    '                            await member.add_roles(role, reason="reaction-role")\n'
    '                        else:\n'
    '                            await member.remove_roles(role, reason="reaction-role")\n'
    '                        entry["applied"] = True\n'
    '                    except Exception:  # noqa: BLE001\n'
    '                        entry["applied"] = False\n'
    '                else:\n'
    '                    entry["applied"] = False\n'
    '            audit_log(ctx.audit_path, entry)\n'
    '        except Exception:  # noqa: BLE001 — reaction handling must never crash the gateway\n'
    '            pass\n'
    '\n'
    '    @client.event\n'
    '    async def on_raw_reaction_add(payload):  # noqa: ANN001 — reaction-roles-d\n'
    '        await _reaction_role_apply(payload, event_type="add")\n'
    '\n'
    '    @client.event\n'
    '    async def on_raw_reaction_remove(payload):  # noqa: ANN001 — reaction-roles-d\n'
    '        await _reaction_role_apply(payload, event_type="remove")\n'
    '\n'
    '    async def _mail_drain_once() -> None:'
)
patch(bot_path, "def _reaction_role_apply(payload", old_handlers, new_handlers, "reaction-role gateway handlers")

# ── 4. COMMANDS catalog — /reaction-role-panel ───────────────────────────────
patch(
    bot_path,
    '("/reaction-role-panel"',
    '    ("/reaction-role-list", "🎭 List reaction-role bindings.", "team"),\n]',
    '    ("/reaction-role-list", "🎭 List reaction-role bindings.", "team"),\n'
    '    ("/reaction-role-panel", "🎭 Post a reaction-role panel with up to 5 options in one shot.", "team"),\n]',
    "reaction-role-panel COMMANDS entry",
)

# ── 5. /reaction-role-panel command — beside reaction-role-list ─────────────
old_panel = (
    '            lines = [f"• msg {b[\'message_id\']} — {b[\'emoji_display\']} → role {b[\'role_id\']}"\n'
    '                     for b in bindings[:25]]\n'
    '            await interaction.response.send_message("🎭 bindings:\\n" + "\\n".join(lines), ephemeral=True)\n'
    '\n'
    '        @tree.command(name="my-panel",'
)
new_panel = (
    '            lines = [f"• msg {b[\'message_id\']} — {b[\'emoji_display\']} → role {b[\'role_id\']}"\n'
    '                     for b in bindings[:25]]\n'
    '            await interaction.response.send_message("🎭 bindings:\\n" + "\\n".join(lines), ephemeral=True)\n'
    '\n'
    '        @tree.command(name="reaction-role-panel",\n'
    '                      description="🎭 Post a reaction-role panel with up to 5 options in one shot.")\n'
    '        @discord.app_commands.describe(\n'
    '            title="panel title", emoji1="first emoji", role1="role for the first emoji",\n'
    '            description="panel description (optional)",\n'
    '            emoji2="second emoji (optional)", role2="role for the second emoji (optional)",\n'
    '            emoji3="third emoji (optional)", role3="role for the third emoji (optional)",\n'
    '            emoji4="fourth emoji (optional)", role4="role for the fourth emoji (optional)",\n'
    '            emoji5="fifth emoji (optional)", role5="role for the fifth emoji (optional)",\n'
    '        )\n'
    '        async def reaction_role_panel_cmd(\n'
    '            interaction, title: str, emoji1: str, role1: discord.Role,\n'
    '            description: str = "",\n'
    '            emoji2: str = "", role2: discord.Role = None,\n'
    '            emoji3: str = "", role3: discord.Role = None,\n'
    '            emoji4: str = "", role4: discord.Role = None,\n'
    '            emoji5: str = "", role5: discord.Role = None,\n'
    '        ):\n'
    '            _remember(interaction.user)\n'
    '            if not _is_staff(interaction):\n'
    '                await interaction.response.send_message("team only.", ephemeral=True)\n'
    '                return\n'
    '            from sovereign_agent import reaction_roles as _rr\n'
    '            pairs = [(emoji1, role1)]\n'
    '            for e, r in ((emoji2, role2), (emoji3, role3), (emoji4, role4), (emoji5, role5)):\n'
    '                if e and r is not None:\n'
    '                    pairs.append((e, r))\n'
    '            keys = [_rr.emoji_key(getattr(e, "id", None), str(e)) for e, _r in pairs]\n'
    '            try:\n'
    '                _rr.validate_panel_options(keys)\n'
    '            except ValueError as exc:\n'
    '                await interaction.response.send_message(f"refusing to post: {exc}", ephemeral=True)\n'
    '                return\n'
    '            lines = [f"{e} \\u2014 {r.mention}" for e, r in pairs]\n'
    '            emb = discord.Embed(\n'
    '                title=title,\n'
    '                description=(description or "React below to get a role.") + "\\n\\n" + "\\n".join(lines),\n'
    '                color=0x5865F2)\n'
    '            message = await interaction.channel.send(embed=emb)\n'
    '            for e, _r in pairs:\n'
    '                try:\n'
    '                    await message.add_reaction(e)\n'
    '                except Exception:  # noqa: BLE001\n'
    '                    pass\n'
    '            for (e, r), key in zip(pairs, keys):\n'
    '                _rr.add_binding(\n'
    '                    data_dir, str(interaction.guild.id), message_id=str(message.id),\n'
    '                    channel_id=str(interaction.channel.id), emoji_key=key, emoji_display=str(e),\n'
    '                    role_id=str(r.id), created_by=str(interaction.user.id))\n'
    '            audit_log(ctx.audit_path, {"op": "reaction_role_panel", "action": "create",\n'
    '                                       "guild_id": str(interaction.guild.id),\n'
    '                                       "message_id": str(message.id), "options": len(pairs)})\n'
    '            await interaction.response.send_message(\n'
    '                f"panel posted with {len(pairs)} option(s).", ephemeral=True)\n'
    '\n'
    '        @tree.command(name="my-panel",'
)
patch(bot_path, 'name="reaction-role-panel"', old_panel, new_panel, "reaction-role-panel slash command")
PYEOF

echo "→ compile check"
VENV_PY="$ROOT/.venv/bin/python"
"$VENV_PY" -m py_compile "$PKG"/reaction_roles/*.py "$BOT"
echo "  ✓ compiles"

echo "→ installing tests"
[[ -f "$HERE/tests/test_reaction_roles.py" ]] && cp "$HERE/tests/test_reaction_roles.py" "$ROOT/tests/"
"$VENV_PY" -m py_compile "$ROOT/tests/test_reaction_roles.py"
echo "  ✓ tests compile"

echo
echo "✓ done. verify:"
echo "    .venv/bin/python -m pytest tests/test_reaction_roles.py -v"
echo "    .venv/bin/python -m pytest tests/test_discord_admin.py -v   # catalog/tier regression net"
