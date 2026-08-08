#!/usr/bin/env python3
import sys

def replace_else_block(filepath):
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    # Find the line with "else:"
    for i, line in enumerate(lines):
        if line.rstrip() == "else:":
            # Find the end of the else block (next line with same indent that is not empty or comment?)
            # Actually, we know the else block is just one line: the atelier_log.write
            # Replace that line and add our new lines after it
            indent = len(line) - len(line.lstrip())
            # Replace the else line and the next line (which should be the atelier_log.write)
            # But let's be safe: replace from the else line until we find a line with less indent that is not empty
            j = i + 1
            while j < len(lines) and (len(lines[j]) - len(lines[j].lstrip()) >= indent and lines[j].strip() != ''):
                j += 1
            # Now replace lines[i:j] with new content
            new_lines = [
                '        else:\n',
                '            self._atelier_log.write(f"[dim]{ts}[/dim] [dim]{\\'\\'\\'}.get(\\'flag\\', \\'\\'\\')}[\\'\\'\\'\\'\\']\"\"\n'
            ]
            # Actually, let's reconstruct properly
            new_block = [
                '        else:\n',
                '            self._atelier_log.write(f"[dim]{ts}[/dim] [dim]{ev.get(\\\"flag\\", \\"\\")}[/dim]")\n',
                '            \n',
                '            # Also send a summary to the main chat (live events) for transparency\n',
                '            if op == "write":\n',
                '                added = payload.get("added", 0)\n',
                '                self._events_log.write(f"[dim]{ts}[/dim] [green]✓ Created {path} (+{added} lines)[/green]")\n',
                '            elif op == "edit":\n',
                '                added = payload.get("added", 0)\n',
                '                removed = payload.get("removed", 0)\n',
                '                self._events_log.write(f"[dim]{ts}[/dim] [yellow]~ Modified {path} (+{added}/-{removed})[/yellow]")\n',
                '            elif op == "command":\n',
                '                cmd = payload.get("cmd", "")\n',
                '                self._events_log.write(f"[dim]{ts}[/dim] [blue]$ Executed: {cmd}[/blue]")\n',
                '            elif op == "media":\n',
                '                kind = payload.get("kind", "media")\n',
                '                detail = payload.get("detail", "")\n',
                '                if detail:\n',
                '                    self._events_log.write(f"[dim]{ts}[/dim] [magenta]✦ Generated {kind}: {detail}[/magenta]")\n',
                '                else:\n',
                '                    self._events_log.write(f"[dim]{ts}[/dim] [magenta]✦ Generated {kind}[/magenta]")\n'
            ]
            # But we need to keep the original indentation level (8 spaces? actually it's 8*2=16? Let's see)
            # The method is indented with 4 spaces, the if/elif inside are with 8 spaces.
            # We'll just write the exact strings as above with proper indentation.
            # Let's instead do a simpler approach: replace the else line and the next line only.
            # Since we know the else block is just one line.
            # Actually, let's look at the file to be sure.
            break
    
    # For simplicity, let's just do a string replace for the known pattern.
    with open(filepath, 'r') as f:
        content = f.read()
    
    old_str = '''        else:
            self._atelier_log.write(f"[dim]{ts}[/dim] [dim]{ev.get('flag', '')}[/dim]")'''
    
    new_str = '''        else:
            self._atelier_log.write(f"[dim]{ts}[/dim] [dim]{ev.get('flag', '')}[/dim]")
        
        # Also send a summary to the main chat (live events) for transparency
        if op == "write":
            added = payload.get("added", 0)
            self._events_log.write(f"[dim]{ts}[/dim] [green]✓ Created {path} (+{added} lines)[/green]")
        elif op == "edit":
            added = payload.get("added", 0)
            removed = payload.get("removed", 0)
            self._events_log.write(f"[dim]{ts}[/dim] [yellow]~ Modified {path} (+{added}/-{removed})[/yellow]")
        elif op == "command":
            cmd = payload.get("cmd", "")
            self._events_log.write(f"[dim]{ts}[/dim] [blue]$ Executed: {cmd}[/blue]")
        elif op == "media":
            kind = payload.get("kind", "media")
            detail = payload.get("detail", "")
            if detail:
                self._events_log.write(f"[dim]{ts}[/dim] [magenta]✦ Generated {kind}: {detail}[/magenta]")
            else:
                self._events_log.write(f"[dim]{ts}[/dim] [magenta]✦ Generated {kind}[/magenta]"'''
    
    if old_str in content:
        content = content.replace(old_str, new_str)
        with open(filepath, 'w') as f:
            f.write(content)
        print("Replaced successfully")
    else:
        print("String not found, trying alternative...")
        # Try with slightly different spacing
        import re
        pattern = r'else:\s*self\._atelier_log\.write\(f"\$$dim\$$\{ts\}\$$dim\$$\ \$$dim\$$\{ev\.get\(\'filter\', \'\'\}\)\}\$$dim\/\$$dim\$$\""\)'
        # Actually, let's just do a more robust search
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if line.strip() == 'else:' and i+1 < len(lines) and '_atelier_log.write' in lines[i+1]:
                # Found it
                indent = len(line) - len(line.lstrip())
                new_lines = [
                    line,  # else:
                    ' ' * (indent + 4) + 'self._atelier_log.write(f"[dim]{ts}[/dim] [dim]{ev.get(\\'\\'\\'flag\\'\\'\\', \\'\\'\\')}[/dim]")',
                    '',
                    ' ' * (indent + 4) + '# Also send a summary to the main chat (live events) for transparency',
                    ' ' * (indent + 4) + 'if op == "write":',
                    ' ' * (indent + 8) + 'added = payload.get("added", 0)',
                    ' ' * (indent + 8) + 'self._events_log.write(f"[dim]{ts}[/dim] [green]✓ Created {path} (+{added} lines)[/green]")',
                    ' ' * (indent + 4) + 'elif op == "edit":',
                    ' ' * (indent + 8) + 'added = payload.get("added", 0)',
                    ' ' * (indent + 8) + 'removed = payload.get("removed", 0)',
                    ' ' * (indent + 8) + 'self._events_log.write(f"[dim]{ts}[/dim] [yellow]~ Modified {path} (+{added}/-{removed})[/yellow]")',
                    ' ' * (indent + 4) + 'elif op == "command":',
                    ' ' * (indent + 8) + 'cmd = payload.get("cmd", "")',
                    ' ' * (indent + 8) + 'self._events_log.write(f"[dim]{ts}[/dim] [blue]$ Executed: {cmd}[/blue]")',
                    ' ' * (indent + 4) + 'elif op == "media":',
                    ' ' * (indent + 8) + 'kind = payload.get("kind", "media")',
                    ' ' * (indent + 8) + 'detail = payload.get("detail", "")',
                    ' ' * (indent + 12) + 'if detail:',
                    ' ' * (indent + 16) + 'self._events_log.write(f"[dim]{ts}[/dim] [magenta]✦ Generated {kind}: {detail}[/magenta]")',
                    ' ' * (indent + 12) + 'else:',
                    ' ' * (indent + 16) + 'self._events_log.write(f"[dim]{ts}[/dim] [magenta]✦ Generated {kind}[/magenta]")'
                ]
                lines[i:i+2] = new_lines
                content = '\n'.join(lines)
                with open(filepath, 'w') as f:
                    f.write(content)
                print("Replaced successfully with line-by-line")
                return
        print("Could not find the pattern")

if __name__ == '__main__':
    replace_else_block('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/cockpit/app.py')