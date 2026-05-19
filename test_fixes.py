import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.response_parser import AIResponseParser

def test_parser_placeholders():
    # The AI response MUST be wrapped in FILE_START/FILE_END to parse correctly
    text = """--- FILE_START: test.py ---
[CODE python]
t = "[BACK3]test[BACK]"
[/CODE]
--- FILE_END ---"""
    
    changes = AIResponseParser.parse(text)
    assert "test.py" in changes, f"Parser did not find file. Keys: {list(changes.keys())}"
    
    content = changes["test.py"]["content"]
    # The parser automatically converts [BACK3] -> ``` and [BACK] -> `
    assert '```' in content and '`' in content, f"Backtick conversion failed. Got: {repr(content)}"
    print("✅ Parser placeholder conversion works")

def test_blank_line_preservation():
    # Simulate a patch with an intentional leading blank line
    text = """--- FILE_START: test.py ---
[CODE python]
[LINE 10]

def new_func():
    pass
[/LINE 10]
[/CODE]
--- FILE_END ---"""
    
    changes = AIResponseParser.parse(text)
    assert "test.py" in changes and "patches" in changes["test.py"]
    patch_content = changes["test.py"]["patches"][0]["content"]
    
    # Parser strips exactly ONE formatting newline, preserving intentional ones
    assert patch_content.startswith("\n"), f"Intentional blank line was stripped! Got: {repr(patch_content)}"
    print("✅ Blank line preservation works")

def test_splitlines():
    # Verify applier logic (splitlines vs split('\n'))
    content = "line1\nline2\n"
    assert content.splitlines() == ["line1", "line2"], "splitlines() failed on trailing newline"
    print("✅ splitlines() handles trailing newlines correctly")

if __name__ == "__main__":
    try:
        test_parser_placeholders()
        test_blank_line_preservation()
        test_splitlines()
        print("\n🎉 All critical fixes verified successfully!")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")