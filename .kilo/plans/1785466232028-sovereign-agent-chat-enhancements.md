# Sovereign Agent Chat System — Kilo-Style Enhancement Plan

**Date:** 2026-07-30
**Status:** Draft — ready for review before implementation
**Scope:** Enhance the existing Textual cockpit chat to feel like Kilo CLI's interactive chat experience

---

## 1. Current State vs. Target Experience

### Current (Sovereign Agent Cockpit)
- 5-pane layout: chat | memory | live | inbox | atelier
- Chat pane = `RichLog` (append-only log, no message structure)
- Input = `RippleInput` (single-line, basic)
- Output = raw log lines with markup
- No message bubbles, no conversation threading
- No streaming responses
- Context not visibly preserved between messages

### Target (Kilo CLI Chat Experience)
- Interactive, persistent conversation with visible history
- Rich output: panels, tables, syntax highlighting, structured sections
- Message bubbles/cards with clear user/assistant distinction
- Streaming responses (token-by-token)
- Command palette integration (Ctrl+K style)
- Context awareness shown to user
- Keyboard-driven workflow

---

## 2. Enhancement Proposals (Priority Order)

### 2.1 — Conversational Message Components (High Priority)

**Problem:** Current chat is a flat `RichLog` — no visual distinction between user/assistant messages, no threading, no rich formatting per message.

**Solution:** Replace `RichLog` with a custom `ChatLog` widget that renders messages as structured components.

**Components to create:**
- `ChatMessage` widget — renders a single message with:
  - Role badge (User / Aria / System / Tool)
  - Timestamp
  - Rich content (markdown, code blocks, tables, panels)
  - Tool call/result expandable sections
  - Token usage / metadata footer (optional)
- `ChatLog` widget — vertical list of `ChatMessage` with:
  - Auto-scroll to bottom on new messages
  - Keyboard navigation (j/k, pgup/pgdown)
  - Message selection for copy/quote
  - Virtual scrolling for performance (1000+ messages)

**Files to create:**
- `src/sovereign_agent/cockpit/chat_message.py`
- `src/sovereign_agent/cockpit/chat_log.py`

**Files to modify:**
- `src/sovereign_agent/cockpit/app.py` — replace `RichLog(id="chat-log")` with `ChatLog(id="chat-log")`

---

### 2.2 — Streaming Response Support (High Priority)

**Problem:** Responses appear all at once after full generation. No token-by-token streaming.

**Solution:** Integrate Ollama's streaming API and render incrementally.

**Approach:**
1. Modify `converse()` in `conversation.py` to yield partial responses
2. Add `stream_chunk` callback to `converse()` signature
3. In cockpit, create a "streaming message" that updates in-place
4. Use Textual's `call_later` / `set_interval` for smooth updates

**Files to modify:**
- `src/sovereign_agent/conversation.py` — add streaming callback
- `src/sovereign_agent/ollama_client.py` — use `ollama.chat(stream=True)`
- `src/sovereign_agent/cockpit/app.py` — handle streaming in `on_input_submitted`

---

### 2.3 — Enhanced Input Experience (High Priority)

**Problem:** Single-line `RippleInput` with no history, autocomplete, or multi-line support.

**Solution:** Build a `ChatInput` widget with:
- Multi-line support (Shift+Enter for newline, Enter to send)
- Command history (up/down arrows)
- Slash-command autocomplete (`/help`, `/tools`, `/memory`, etc.)
- Tool call preview before execution
- Token count estimate
- Paste handling (multi-line)

**Files to create:**
- `src/sovereign_agent/cockpit/chat_input.py`

**Files to modify:**
- `src/sovereign_agent/cockpit/app.py` — replace `RippleInput` with `ChatInput`

---

### 2.4 — Rich Output Rendering Pipeline (Medium Priority)

**Problem:** Tool outputs, code, tables render as plain text in RichLog.

**Solution:** Add a rendering pipeline that detects content types and renders appropriately:
- Code blocks → syntax-highlighted `Syntax` widget
- Tables → `DataTable` (interactive)
- JSON → collapsible tree view
- File diffs → side-by-side diff view
- Tool calls → structured cards with expandable args/results
- Errors → red-bordered panels with copy button

**Files to create:**
- `src/sovereign_agent/cockpit/renderers.py` — renderer registry + built-in renderers

---

### 2.5 — Conversation Context Visualization (Medium Priority)

**Problem:** User can't see what context Aria has (memory channels, active project, mode, tier).

**Solution:** Add a context bar above chat showing:
- Active mode (oneshot/busy/auto/chat)
- Authority tier ceiling
- Memory channels with counts
- Active project
- Token budget used/remaining

**Files to create:**
- `src/sovereign_agent/cockpit/context_bar.py`

---

### 2.6 — Command Palette Integration (Medium Priority)

**Problem:** Command palette exists but isn't integrated into chat flow like Kilo's Ctrl+K.

**Solution:**
- Bind `Ctrl+K` to open command palette over chat
- Palette shows: recent commands, slash-commands, tool shortcuts, memory queries
- Selecting a command pre-fills input (like current palette) but with preview

**Files to modify:**
- `src/sovereign_agent/cockpit/app.py` — add `action_command_palette` binding
- `src/sovereign_agent/cockpit/command_palette_screen.py` — enhance with chat context

---

### 2.7 — Message Actions & Threading (Low Priority)

**Problem:** No way to reply to, quote, copy, or branch from a specific message.

**Solution:** Add message toolbar on hover/focus:
- Reply (starts new message quoting selected)
- Copy (markdown or plain text)
- Branch (fork conversation from this message)
- View raw event JSON
- Toggle tool call details

---

## 3. Implementation Order

| Phase | Enhancement | Dependencies | Effort |
|-------|-------------|--------------|--------|
| 1 | Conversational Message Components (2.1) | None | Medium |
| 2 | Streaming Response Support (2.2) | 2.1 | Medium |
| 3 | Enhanced Input Experience (2.3) | 2.1 | Medium |
| 4 | Rich Output Rendering (2.4) | 2.1 | Large |
| 5 | Context Visualization (2.5) | 2.1 | Small |
| 6 | Command Palette Integration (2.6) | 2.1, 2.3 | Small |
| 7 | Message Actions (2.7) | 2.1 | Medium |

---

## 4. Key Technical Decisions

### 4.1 — Preserve Existing Architecture
- Keep `conversation.py` as the core logic layer
- Keep `RichLog` fallback for compatibility
- Don't change the event/logging pipeline (events.jsonl tailing)

### 4.2 — Streaming Integration Point
The cleanest integration is in `conversation.py`'s `converse()` function:
```python
async def converse(
    text: str,
    *,
    ollama_client: Any = None,
    stream_callback: Callable[[str], None] | None = None,  # NEW
    ...
) -> Turn:
```
When `stream_callback` is provided, yield partial responses instead of waiting for full.

### 4.3 — Widget Hierarchy
```
ChatLog (VerticalScroll)
├── ChatMessage (User)
│   ├── RoleBadge
│   ├── Content (Markdown/Syntax)
│   └── MetaFooter
├── ChatMessage (Assistant)
│   ├── RoleBadge
│   ├── Content (streaming Markdown)
│   ├── ToolCallCard (expandable)
│   └── MetaFooter
└── ...
```

### 4.4 — Performance
- Virtual scrolling: only render visible messages + buffer
- Message pooling: reuse widgets for scrolling
- Lazy markdown parsing: parse on first render, cache

---

## 5. Validation Plan

1. **Visual regression** — Screenshots of chat with various message types
2. **Streaming test** — Verify token-by-token rendering with 50+ token response
3. **History test** — 500 messages scroll performance (60fps)
4. **Input test** — Multi-line, history, autocomplete all work
5. **Integration test** — `sov chat send "hello"` still works via CLI
6. **Fallback test** — RichLog still works if new widgets fail

---

## 6. Open Questions

1. **Streaming vs. tool calls** — Should tool calls stream too, or only final response?
2. **Markdown in streaming** — Render partial markdown incrementally or wait for complete?
3. **Message persistence** — Should chat history survive cockpit restart? (Currently in events.jsonl)
4. **Theme integration** — Use existing `aria-*` themes or define chat-specific styles?
5. **Accessibility** — Screen reader support for message roles and tool calls?

---

## 7. Minimal Viable First Step

If only one thing can be done first: **Phase 1 (2.1 + 2.3)** — Structured message components + enhanced input. This alone transforms the chat from a log viewer into a conversational interface.

The streaming (2.2) can layer on top once messages are structured components.