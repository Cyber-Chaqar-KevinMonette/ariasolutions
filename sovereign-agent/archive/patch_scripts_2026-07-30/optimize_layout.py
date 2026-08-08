#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/cockpit/app.py', 'r') as f:
    content = f.read()

# Fix 1: Reduce chat log max_lines to fit on one screen
old1 = '''                yield RichLog(
                    id="chat-log",
                    highlight=True, markup=True, wrap=True,
                    auto_scroll=True, max_lines=1000,
                    min_width=1,
                )'''

new1 = '''                yield RichLog(
                    id="chat-log",
                    highlight=True, markup=True, wrap=True,
                    auto_scroll=True, max_lines=200,
                    min_width=1,
                )'''

content = content.replace(old1, new1)

# Fix 2: Make palette row more compact
old2 = '''        with Horizontal(id="palette-row"):
            yield MenuTriggerButton("⋮ commands", id="palette-menu-btn")  # stuck-highlight-fix-d
            yield MenuTriggerButton("▫ view", id="quick-view-btn")  # button-focus-fix-d
            yield MenuTriggerButton("\\u25aa layout", id="layout-cycle-btn")  # view-selectors-d
            yield MenuTriggerButton("@ session", id="session-setup-btn")  # session-setup-unify-d
            yield MenuTriggerButton("+1h", id="add-time-btn")  # mid-session-add-time-d
            # discord-control-d (Kevin, 2026-07-25): "a way for me to
            # control the bot... maybe a menu and a button next to the 1
            # hour button." "an instructions button next to the new
            # discord button... a third button to make the game window
            # go away."
            # glyph-fix-d (Kevin, 2026-07-26): the old ⛁ (WHITE DRAUGHTS
            # KING) tested emoji-risk via unicodedata + glyphs.is_emoji_risk
            # (never actually vetted despite shipping) — some terminals
            # render it as a colorful pictograph, not one plain cell. ❖ is
            # glyphs.py's own catalogued "brand-safe alternate".
            yield MenuTriggerButton("❖ discord", id="discord-control-btn")  # discord-control-d
            # my-inbox-d (Kevin, 2026-07-26): "a my inbox menu button and a
            # my inbox menu where I can reply to my inbox messages
            # directly." Beside the other new buttons, next to the games
            # one, per his own placement.
            yield MenuTriggerButton("& my inbox", id="my-inbox-btn")  # my-inbox-d
            # suggestions-d (Kevin, 2026-07-26): "so when I want to ask her
            # for things she could or would like to work on — she could
            # give me a list of important and/or valuable task she can
            # work on or practice doing." Grounded in real sentinel
            # findings + unbuilt bot ideas, never invented.
            yield MenuTriggerButton("✧ suggestions", id="suggestions-btn")  # suggestions-d
            # task-guide-d (Kevin, 2026-07-26): "Create a menu for things
            # she can do... a task guide button on the frontend so I can
            # see everything I can do with her and so I can test
            # everything following the guide." Grounded in the real tool
            # registry (task_guide.py), never invented.
            yield MenuTriggerButton("% guide", id="task-guide-btn")  # task-guide-d
            # stripe-links-d (Kevin, 2026-07-26): "add a button and menu for
            # stripe control panel inside the cockpit front end so I can see
            # all the current stripe links... like a stripe links vault."
            # ASCII-only glyph per the hard-won glyph-safety lesson this
            # session (Unicode "verified-safe" glyphs kept rendering broken
            # on Kevin's actual terminal).
            yield MenuTriggerButton("$ stripe", id="stripe-links-btn")  # stripe-links-d
            # source-toggle-d (Kevin, 2026-07-27): "Make a control panel
            # where I can turn sources on and off. I want to toggle
            # reddit off." Source.enabled already existed and was
            # already respected by the poll loop — nothing let an
            # operator flip it until now.
            yield MenuTriggerButton("# sources", id="sources-control-btn")  # source-toggle-d
            yield MenuTriggerButton("? help", id="instructions-btn")  # instructions-d
            yield MenuTriggerButton("✦ game", id="game-toggle-btn")  # game-window-optional-d
            # movie-focus-d (Kevin, 2026-07-28): "add a movie studio button
            # next to the game button and a pause all bots button next to
            # the movie button" — a direct-access pair for GPU-heavy movie
            # work: open Movie Studio, then quiet the Discord bots so
            # nothing competes for RAM/VRAM during a render (the exact
            # manual systemctl dance done by hand earlier tonight).
            yield MenuTriggerButton("✦ movie", id="movie-toggle-btn")  # movie-focus-d
            # glyph-fix-d (Kevin, 2026-07-28): ⏸ (U+23F8 PAUSE) was ALREADY
            # flagged by Kevin on 2026-07-20 (see glyphs.py's own
            # emoji-risk-range comment) as rendering as a broken/tofu box
            # on his terminal -- reused it again without checking that
            # history. ▪ is the exact glyph bot_services.states_line()
            # itself already uses for "stopped" -- proven safe AND
            # semantically apt.
            yield MenuTriggerButton("▪ bots", id="bots-toggle-btn")  # movie-focus-d'''

new2 = '''        with Horizontal(id="palette-row"):
            yield MenuTriggerButton("⋮ commands", id="palette-menu-btn")
            yield MenuTriggerButton("▫ view", id="quick-view-btn")
            yield MenuTriggerButton("\\u25aa layout", id="layout-cycle-btn")
            yield MenuTriggerButton("@ session", id="session-setup-btn")
            yield MenuTriggerButton("+1h", id="add-time-btn")
            yield MenuTriggerButton("❖ discord", id="discord-control-btn")
            yield MenuTriggerButton("& inbox", id="my-inbox-btn")
            yield MenuTriggerButton("✧ ideas", id="suggestions-btn")
            yield MenuTriggerButton("% guide", id="task-guide-btn")
            yield MenuTriggerButton("$ stripe", id="stripe-links-btn")
            yield MenuTriggerButton("# sources", id="sources-control-btn")
            yield MenuTriggerButton("? help", id="instructions-btn")
            yield MenuTriggerButton("✦ game", id="game-toggle-btn")
            yield MenuTriggerButton("✦ movie", id="movie-toggle-btn")
            yield MenuTriggerButton("▪ bots", id="bots-toggle-btn")'''

content = content.replace(old2, new2)

with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/cockpit/app.py', 'w') as f:
    f.write(content)
print("Successfully optimized layout for single-screen fit")