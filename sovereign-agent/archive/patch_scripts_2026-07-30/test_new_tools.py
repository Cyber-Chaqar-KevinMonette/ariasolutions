#!/usr/bin/env python3
"""Test script to verify the new tools work correctly."""
import asyncio
import tempfile
import os
from pathlib import Path

from sovereign_agent.tools import GlobTool, GrepTool, ReadTool, EditTool


async def test_tools():
    """Test all the new tools."""
    # Create a temporary directory with some test files
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Create test files
        (tmpdir / "test1.py").write_text("""
def hello_world():
    print("Hello, World!")
    return 42

def add_numbers(a, b):
    return a + b

class Calculator:
    def __init__(self):
        self.value = 0
    
    def add(self, x):
        self.value += x
        return self.value
""")
        
        (tmpdir / "test2.py").write_text("""
import os
import sys

def main():
    print("This is test file 2")
    files = os.listdir('.')
    for f in files:
        if f.endswith('.py'):
            print(f"Python file: {f}")

if __name__ == "__main__":
    main()
""")
        
        (tmpdir / "notes.txt").write_text("""
This is a text file with some notes.
Line 2 of notes
Line 3 of notes
Another line here
Final line
""")
        
        print("=== Testing GlobTool ===")
        glob_tool = GlobTool()
        result = await glob_tool.execute(GlobTool.Args(pattern="**/*.py", root=str(tmpdir)), trace_id="test")
        print(f"Found {len(result.output)} Python files:")
        for file in result.output:
            print(f"  - {file}")
        assert result.ok
        
        print("\n=== Testing GrepTool ===")
        grep_tool = GrepTool()
        result = await grep_tool.execute(GrepTool.Args(pattern="def ", path=str(tmpdir), include="*.py"), trace_id="test")
        print(f"Found {len(result.output)} function definitions:")
        for match in result.output[:3]:  # Show first 3
            print(f"  - {match['file']}:{match['line']}: {match['text'].strip()}")
        assert result.ok
        
        print("\n=== Testing ReadTool ===")
        read_tool = ReadTool()
        result = await read_tool.execute(ReadTool.Args(path=str(tmpdir / "notes.txt"), offset=1, limit=2), trace_id="test")
        print(f"Read lines 2-3 from notes.txt:")
        for line in result.output:
            print(f"  Line {line['line_no']}: {line['text']}")
        assert result.ok
        assert len(result.output) == 2
        
        print("\n=== Testing EditTool ===")
        edit_tool = EditTool()
        
        # Test insert
        result = await edit_tool.execute(EditTool.Args(
            command="insert",
            path=str(tmpdir / "notes.txt"),
            insert_line=1,
            new_str="INSERTED LINE AT BEGINNING"
        ), trace_id="test")
        print(f"Insert result: {result.ok}")
        assert result.ok
        # Read back to verify
        result2 = await read_tool.execute(ReadTool.Args(path=str(tmpdir / "notes.txt")), trace_id="test")
        print("File after insertion:")
        for line in result2.output:
            print(f"  Line {line['line_no']}: {line['text']}")
        assert "INSERTED LINE AT BEGINNING" in result2.output[0]['text']
        
        # Test str_replace
        result = await edit_tool.execute(EditTool.Args(
            command="str_replace",
            path=str(tmpdir / "notes.txt"),
            old_str="INSERTED LINE AT BEGINNING",
            new_str="REPLACED LINE"
        ), trace_id="test")
        print(f"Replace result: {result.ok}")
        assert result.ok
        result2 = await read_tool.execute(ReadTool.Args(path=str(tmpdir / "notes.txt")), trace_id="test")
        print("File after replacement:")
        for line in result2.output:
            print(f"  Line {line['line_no']}: {line['text']}")
        assert "REPLACED LINE" in result2.output[0]['text']
        
        # Test delete - remove the blank line and "This is a text file with some notes."
        result = await edit_tool.execute(EditTool.Args(
            command="delete",
            path=str(tmpdir / "notes.txt"),
            start_line=2,
            end_line=3
        ), trace_id="test")
        print(f"Delete result: {result.ok}")
        assert result.ok
        result2 = await read_tool.execute(ReadTool.Args(path=str(tmpdir / "notes.txt")), trace_id="test")
        print("File after deletion:")
        for line in result2.output:
            print(f"  Line {line['line_no']}: {line['text']}")
        # After deletion:
        # Line 1: REPLACED LINE
        # Line 2: Line 2 of notes  
        # Line 3: Line 3 of notes
        # Line 4: Another line here
        # Line 5: Final line
        assert "Line 2 of notes" in result2.output[1]['text']
        assert "Another line here" in result2.output[3]['text']
        
        print("\n✅ All tests passed!")


if __name__ == "__main__":
    asyncio.run(test_tools())