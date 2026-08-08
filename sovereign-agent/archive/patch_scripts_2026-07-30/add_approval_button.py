#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/cockpit/resume_menu_screen.py', 'r') as f:
    content = f.read()

# Insert the ApprovalButton class after the ForgetSessionButton class
lines = content.split('\n')
insert_pos = None

for i, line in enumerate(lines):
    if 'class ForgetSessionButton' in line:
        # Find the end of the ForgetSessionButton class
        j = i
        while j < len(lines) and (not lines[j].strip().startswith('class ') and 'class' not in lines[j]):
            j += 1
        # Insert after the ForgetSessionButton class
        insert_pos = j
        break

if insert_pos is not None:
    # Insert the new class before the next class or at end
    new_content = '''
class _HandoffButton(Button):
    """A button that fires an action and hands off (closes this modal),
    not a sustained focus target. Local copy of app.py's MenuTriggerButton
    (can't import it directly -- app.py imports THIS module, so importing
    back from .app would be a circular import). Same fix, same reason:
    without can_focus=False, Textual restores the focus ring here forever
    once the modal closes (feedback_cockpit_button_focus)."""
    can_focus = False

    
class ResumeSessionButton(_HandoffButton):
    """One resumable session. Carries its session_id for the click handler."""
    
    def __init__(self, session_id: str, label: str) -> None:
        safe_id = "resume-" + "".join(c if (c.isalnum() or c == "-") else "-" for c in session_id)[-24:]
        super().__init__(label, id=safe_id, classes="resume-choice-btn")
        self.session_id = session_id

class ForgetSessionButton(_HandoffButton):
    """resume-menu-forget-d — a per-row 'forget this session' button so
    Kevin can delete sessions he no longer needs straight from the menu,
    without ever touching the ones he didn't pick."""
    
    def __init__(self, session_id: str) -> None:
        safe_id = "forget-" + "".join(c if (c.isalnum or c == "-") else "-" for c in session_id)[-24:]
        super().__init__("✕ forget", id=safe_id, classes="forget-choice-btn")
        self.session_id = session_id

class ApprovalButton(_HandoffButton):
    """Approval button for held subtasks."""
    
    def __init__(self, session_id: str) -> None:
        safe_id = "approve-" + "".join(c if (c.isalnum or c == "-") else "-" for c in session_id)[-24:]
        super().__init__("✓ approve", id=safe_id, classes="resume-choice-btn")
        self.session_id = session_id

    def action(self) -> None:
        """Handle the click event."""
        self.app._resume_work_session(self.session_id)

class _HandoffButton(Button):
    """A button that fires an action and hands off (closes this modal),
    not a sustained focus target. Local copy of app.py's MenuTriggerButton
    (can't import it directly -- app.py imports THIS module, so importing
    back from .app would be a circular import). Same fix, same reason:
    without can_focus=False, Textual restores the focus ring here forever
    once the modal closes (feedback_cockpit_button_focus)."""
    can_focus = False

"""

content = content.replace(lines[114:135], new_content)
with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/cockpit/resume_menu_screen.py', 'w') as f:
    f.write(content)
print("Successfully added ApprovalButton class")