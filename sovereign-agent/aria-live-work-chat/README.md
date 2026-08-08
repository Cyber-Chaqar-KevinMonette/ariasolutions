# aria-live-work-chat

This reviewable patch turns the existing durable inbox into a real live-work conversation surface.

- Operator messages typed while Aria works are immediately shown in the main chat and safely delivered at the next subtask boundary.
- `send_to_human` messages are live-chat messages by default, shown as Aria in the cockpit within one second and retained in the inbox.
- No active tool call is interrupted; `/halt` remains the immediate-stop path.

Run `./aria-live-work-chat/apply_live_work_chat.sh` only after reviewing it and stopping the cockpit.
