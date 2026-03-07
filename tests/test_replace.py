"""Tests for text replacement logic."""

import pytest
from pathlib import Path

from txt_process.core.replace import apply_replacements, build_output_path


class TestApplyReplacements:
    """Tests for the replacement function."""

    def test_simple_replacement(self):
        """Simple single replacement."""
        text = "张三去了商店。张三买了东西。"
        mappings = {"张三": "李四"}

        result, counts = apply_replacements(text, mappings)

        assert result == "李四去了商店。李四买了东西。"
        assert counts["张三"] == 2

    def test_multiple_replacements(self):
        """Multiple different replacements."""
        text = "张三和李四是朋友。张三很高，李四很矮。"
        mappings = {"张三": "王五", "李四": "赵六"}

        result, counts = apply_replacements(text, mappings)

        assert "王五" in result
        assert "赵六" in result
        assert "张三" not in result
        assert "李四" not in result
        assert counts["张三"] == 2
        assert counts["李四"] == 2

    def test_no_mappings(self):
        """Empty mappings returns original text."""
        text = "Original text."
        mappings = {}

        result, counts = apply_replacements(text, mappings)

        assert result == text
        assert counts == {}

    def test_no_matches(self):
        """Mappings that don't match anything."""
        text = "张三是主角。"
        mappings = {"李四": "王五"}

        result, counts = apply_replacements(text, mappings)

        assert result == text
        assert counts["李四"] == 0

    def test_overlap_safety_longer_first(self):
        """Longer names are replaced before shorter overlapping names.

        This prevents "张三" from breaking "张三丰" into "李四丰".
        """
        text = "张三丰是武林高手。张三是他的朋友。"
        mappings = {
            "张三丰": "无忌爷爷",
            "张三": "李四",
        }

        result, counts = apply_replacements(text, mappings)

        assert "无忌爷爷是武林高手" in result
        assert "李四是他的朋友" in result
        # Verify 张三丰 was replaced correctly (not as 李四丰)
        assert "李四丰" not in result

    def test_overlap_safety_substring(self):
        """Substring names don't break longer names."""
        text = "小明和小明明都来了。"
        mappings = {
            "小明明": "大刚",
            "小明": "小红",
        }

        result, counts = apply_replacements(text, mappings)

        assert "小红和大刚都来了" in result
        assert counts["小明明"] == 1
        assert counts["小明"] == 1

    def test_english_names(self):
        """English name replacement."""
        text = "Alice met Bob. Alice said hello to Bob."
        mappings = {"Alice": "Carol", "Bob": "Dave"}

        result, counts = apply_replacements(text, mappings)

        assert result == "Carol met Dave. Carol said hello to Dave."
        assert counts["Alice"] == 2
        assert counts["Bob"] == 2

    def test_mixed_language(self):
        """Mixed Chinese and English replacement."""
        text = "张三 met Alice at the 咖啡馆。"
        mappings = {"张三": "李四", "Alice": "Bob"}

        result, counts = apply_replacements(text, mappings)

        assert "李四" in result
        assert "Bob" in result

    def test_preserves_formatting(self):
        """Replacement preserves surrounding formatting."""
        text = "「张三」说：\n"你好！"\n\n张三离开了。"
        mappings = {"张三": "李四"}

        result, counts = apply_replacements(text, mappings)

        assert "「李四」" in result
        assert "\n\n李四离开了" in result
        assert counts["张三"] == 2

    def test_edited_only(self):
        """Only mappings that are different are applied.

        Note: The filtering of edited-only happens at the UI/model layer,
        but we verify the function handles its input correctly.
        """
        text = "张三和李四"
        # Simulating: 张三 was edited to 王五, 李四 was not edited
        mappings = {"张三": "王五"}  # Only edited mappings passed in

        result, counts = apply_replacements(text, mappings)

        assert "王五" in result
        assert "李四" in result  # Unchanged
        assert counts["张三"] == 1

    def test_unicode_characters(self):
        """Handle various Unicode characters."""
        text = "张三🎉和李四👍都很开心。"
        mappings = {"张三": "王五", "李四": "赵六"}

        result, counts = apply_replacements(text, mappings)

        assert "王五🎉" in result
        assert "赵六👍" in result

    def test_empty_text(self):
        """Empty text returns empty."""
        result, counts = apply_replacements("", {"张三": "李四"})

        assert result == ""
        assert counts["张三"] == 0


class TestBuildOutputPath:
    """Tests for output path generation."""

    def test_simple_txt(self):
        """Simple .txt file."""
        input_path = Path("/path/to/story.txt")
        result = build_output_path(input_path)

        assert result == Path("/path/to/story_processed.txt")

    def test_no_extension(self):
        """File without extension."""
        input_path = Path("/path/to/story")
        result = build_output_path(input_path)

        assert result == Path("/path/to/story_processed")

    def test_different_extension(self):
        """Non-.txt extension."""
        input_path = Path("/path/to/document.md")
        result = build_output_path(input_path)

        assert result == Path("/path/to/document_processed.md")

    def test_multiple_dots(self):
        """Filename with multiple dots."""
        input_path = Path("/path/to/story.chapter1.txt")
        result = build_output_path(input_path)

        assert result == Path("/path/to/story.chapter1_processed.txt")

    def test_chinese_filename(self):
        """Chinese filename."""
        input_path = Path("/path/to/小说.txt")
        result = build_output_path(input_path)

        assert result == Path("/path/to/小说_processed.txt")

    def test_same_directory(self):
        """Output is in same directory as input."""
        input_path = Path("/some/directory/file.txt")
        result = build_output_path(input_path)

        assert result.parent == input_path.parent

    def test_relative_path(self):
        """Relative path handling."""
        input_path = Path("story.txt")
        result = build_output_path(input_path)

        assert result == Path("story_processed.txt")

    def test_hidden_file(self):
        """Hidden file (starts with dot)."""
        input_path = Path("/path/to/.hidden.txt")
        result = build_output_path(input_path)

        assert result == Path("/path/to/.hidden_processed.txt")
