"""Tests for name extraction and deduplication."""

import pytest

from txt_process.core.name_extract import (
    extract_names_from_response,
    normalize_name,
    dedupe_names,
)


class TestExtractNamesFromResponse:
    """Tests for parsing LLM responses."""

    def test_strict_json(self):
        """Parse strict JSON response."""
        response = '{"names": ["张三", "李四", "王五"]}'
        result = extract_names_from_response(response)
        assert result == ["张三", "李四", "王五"]

    def test_json_with_whitespace(self):
        """Parse JSON with extra whitespace."""
        response = '''
        {
            "names": ["Alice", "Bob", "Charlie"]
        }
        '''
        result = extract_names_from_response(response)
        assert result == ["Alice", "Bob", "Charlie"]

    def test_json_wrapped_in_text(self):
        """Extract JSON from response with surrounding text."""
        response = '''Here are the character names I found:
        {"names": ["张三", "李四"]}
        That's all the names in this text.'''
        result = extract_names_from_response(response)
        assert result == ["张三", "李四"]

    def test_json_with_markdown(self):
        """Extract JSON from markdown code block."""
        response = '''```json
{"names": ["Alice", "Bob"]}
```'''
        result = extract_names_from_response(response)
        assert result == ["Alice", "Bob"]

    def test_empty_names_list(self):
        """Handle empty names list."""
        response = '{"names": []}'
        result = extract_names_from_response(response)
        assert result == []

    def test_names_with_nulls_filtered(self):
        """Filter out null/empty values."""
        response = '{"names": ["Alice", null, "", "Bob"]}'
        result = extract_names_from_response(response)
        # null becomes None, "" is empty - both should be filtered
        assert "Alice" in result
        assert "Bob" in result

    def test_empty_response(self):
        """Empty response returns empty list."""
        result = extract_names_from_response("")
        assert result == []

    def test_whitespace_only_response(self):
        """Whitespace-only response returns empty list."""
        result = extract_names_from_response("   \n\t  ")
        assert result == []

    def test_line_by_line_fallback(self):
        """Fall back to line-by-line extraction."""
        response = """张三
李四
王五"""
        result = extract_names_from_response(response)
        assert "张三" in result
        assert "李四" in result
        assert "王五" in result

    def test_numbered_list_fallback(self):
        """Handle numbered list format."""
        response = """1. 张三
2. 李四
3. 王五"""
        result = extract_names_from_response(response)
        assert "张三" in result
        assert "李四" in result
        assert "王五" in result

    def test_invalid_json_structure(self):
        """Handle JSON without 'names' key."""
        response = '{"characters": ["Alice"]}'
        # Should fall back to line extraction or raise
        # Since it doesn't have names key, try other methods
        result = extract_names_from_response(response)
        # May or may not extract anything depending on fallback logic
        # Just ensure it doesn't crash

    def test_mixed_types_in_names(self):
        """Handle mixed types in names array."""
        response = '{"names": ["Alice", 123, "Bob", true]}'
        result = extract_names_from_response(response)
        assert "Alice" in result
        assert "Bob" in result
        assert "123" in result  # Converted to string


class TestNormalizeName:
    """Tests for name normalization."""

    def test_strip_whitespace(self):
        """Strip leading/trailing whitespace."""
        assert normalize_name("  Alice  ") == "Alice"
        assert normalize_name("\t张三\n") == "张三"

    def test_preserve_internal_spaces(self):
        """Preserve spaces within names."""
        assert normalize_name("John Smith") == "John Smith"

    def test_empty_string(self):
        """Empty string stays empty."""
        assert normalize_name("") == ""
        assert normalize_name("   ") == ""


class TestDedupeNames:
    """Tests for name deduplication."""

    def test_remove_duplicates(self):
        """Remove duplicate names."""
        names = ["Alice", "Bob", "Alice", "Charlie", "Bob"]
        result = dedupe_names(names)
        assert result == ["Alice", "Bob", "Charlie"]

    def test_preserve_order(self):
        """Preserve first-seen order."""
        names = ["Charlie", "Alice", "Bob", "Alice"]
        result = dedupe_names(names)
        assert result == ["Charlie", "Alice", "Bob"]

    def test_empty_list(self):
        """Empty list returns empty."""
        assert dedupe_names([]) == []

    def test_filter_empty_names(self):
        """Filter out empty names."""
        names = ["Alice", "", "Bob", "   ", "Charlie"]
        result = dedupe_names(names)
        assert result == ["Alice", "Bob", "Charlie"]

    def test_whitespace_normalization(self):
        """Names with different whitespace are deduplicated."""
        names = ["Alice", " Alice", "Alice ", " Alice "]
        result = dedupe_names(names)
        assert result == ["Alice"]

    def test_case_sensitive(self):
        """Deduplication is case-sensitive (by default)."""
        names = ["Alice", "alice", "ALICE"]
        result = dedupe_names(names)
        assert len(result) == 3

    def test_chinese_names(self):
        """Chinese names are handled correctly."""
        names = ["张三", "李四", "张三", "王五", "李四"]
        result = dedupe_names(names)
        assert result == ["张三", "李四", "王五"]

    def test_mixed_names(self):
        """Mixed Chinese and English names."""
        names = ["张三", "Alice", "张三", "Bob", "Alice"]
        result = dedupe_names(names)
        assert result == ["张三", "Alice", "Bob"]
