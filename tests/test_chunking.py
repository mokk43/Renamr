"""Tests for text chunking."""

import pytest

from txt_process.core.chunking import (
    split_into_paragraphs,
    split_into_chunks,
    _byte_length,
    _split_by_bytes,
    DEFAULT_CHUNK_MAX_BYTES,
)


class TestSplitIntoParagraphs:
    """Tests for paragraph splitting."""

    def test_empty_text(self):
        """Empty text returns empty list."""
        assert split_into_paragraphs("") == []
        assert split_into_paragraphs("   ") == []
        assert split_into_paragraphs("\n\n\n") == []

    def test_single_paragraph(self):
        """Single paragraph without blank lines."""
        text = "This is a single paragraph.\nWith multiple lines."
        result = split_into_paragraphs(text)
        assert len(result) == 1
        assert "single paragraph" in result[0]

    def test_multiple_paragraphs(self):
        """Multiple paragraphs separated by blank lines."""
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        result = split_into_paragraphs(text)
        assert len(result) == 3
        assert result[0] == "First paragraph."
        assert result[1] == "Second paragraph."
        assert result[2] == "Third paragraph."

    def test_multiple_blank_lines(self):
        """Multiple consecutive blank lines should still separate."""
        text = "Para 1.\n\n\n\nPara 2."
        result = split_into_paragraphs(text)
        assert len(result) == 2

    def test_windows_line_endings(self):
        """Windows CRLF line endings are handled."""
        text = "Para 1.\r\n\r\nPara 2."
        result = split_into_paragraphs(text)
        assert len(result) == 2

    def test_chinese_text(self):
        """Chinese text paragraphs work correctly."""
        text = "第一段落。包含中文。\n\n第二段落。也有中文。"
        result = split_into_paragraphs(text)
        assert len(result) == 2
        assert "第一段落" in result[0]
        assert "第二段落" in result[1]


class TestByteLength:
    """Tests for byte length calculation."""

    def test_ascii(self):
        """ASCII characters are 1 byte each."""
        assert _byte_length("hello") == 5

    def test_chinese(self):
        """Chinese characters are 3 bytes each in UTF-8."""
        assert _byte_length("你好") == 6

    def test_mixed(self):
        """Mixed ASCII and Chinese."""
        text = "Hello你好"
        assert _byte_length(text) == 5 + 6  # 5 ASCII + 2 Chinese (3 bytes each)


class TestSplitByBytes:
    """Tests for byte-level splitting."""

    def test_small_text(self):
        """Text smaller than limit stays intact."""
        result = _split_by_bytes("hello", 100)
        assert result == ["hello"]

    def test_exact_split(self):
        """Text is split correctly at byte boundaries."""
        # Each Chinese char is 3 bytes
        text = "一二三四五"  # 15 bytes
        result = _split_by_bytes(text, 10)  # Max 9 bytes per chunk
        # Should get chunks of 3 chars (9 bytes) each
        assert len(result) == 2
        assert result[0] == "一二三"
        assert result[1] == "四五"


class TestSplitIntoChunks:
    """Tests for the main chunking function."""

    def test_empty_text(self):
        """Empty text returns empty list."""
        assert split_into_chunks("") == []
        assert split_into_chunks("   ") == []

    def test_small_text_single_chunk(self):
        """Small text fits in one chunk."""
        text = "This is a small text.\n\nWith two paragraphs."
        result = split_into_chunks(text, max_bytes=1000)
        assert len(result) == 1
        assert "small text" in result[0]
        assert "two paragraphs" in result[0]

    def test_paragraphs_grouped_into_chunks(self):
        """Multiple paragraphs are grouped into chunks under the limit."""
        # Create text with several small paragraphs
        paragraphs = ["Paragraph number {}.".format(i) for i in range(10)]
        text = "\n\n".join(paragraphs)

        # Use a limit that can fit ~3 paragraphs
        result = split_into_chunks(text, max_bytes=100)

        # Should have multiple chunks
        assert len(result) > 1

        # All chunks should be under the limit
        for chunk in result:
            assert _byte_length(chunk) < 100

    def test_all_chunks_under_limit(self):
        """All chunks must be strictly under the byte limit."""
        # Create a larger text
        text = "这是一个测试段落。" * 100 + "\n\n" + "另一个段落。" * 100

        limit = 500
        result = split_into_chunks(text, max_bytes=limit)

        for i, chunk in enumerate(result):
            byte_size = _byte_length(chunk)
            assert byte_size < limit, f"Chunk {i} is {byte_size} bytes, limit is {limit}"
            assert byte_size > 0, f"Chunk {i} is empty"

    def test_oversized_paragraph_is_split(self):
        """A single oversized paragraph is split into sub-chunks."""
        # Create a paragraph that's definitely over 100 bytes
        paragraph = "这是一个很长的段落。" * 50  # About 900 bytes

        limit = 100
        result = split_into_chunks(paragraph, max_bytes=limit)

        assert len(result) > 1
        for chunk in result:
            assert _byte_length(chunk) < limit

    def test_preserves_order(self):
        """Chunks preserve the original text order."""
        text = "First.\n\nSecond.\n\nThird.\n\nFourth.\n\nFifth."
        result = split_into_chunks(text, max_bytes=30)

        # Concatenate chunks and check order
        all_text = " ".join(result)
        first_pos = all_text.find("First")
        second_pos = all_text.find("Second")
        third_pos = all_text.find("Third")
        fourth_pos = all_text.find("Fourth")
        fifth_pos = all_text.find("Fifth")

        assert first_pos < second_pos < third_pos < fourth_pos < fifth_pos

    def test_default_limit_is_16kb(self):
        """Default chunk limit is 16KB."""
        assert DEFAULT_CHUNK_MAX_BYTES == 16 * 1024

    def test_realistic_novel_chunking(self):
        """Simulate chunking a novel-like text."""
        # Create ~50KB of text with multiple paragraphs
        paragraph = "这是小说中的一个段落。张三和李四在讨论事情。" * 10
        paragraphs = [paragraph for _ in range(30)]
        text = "\n\n".join(paragraphs)

        # Use default 16KB limit
        result = split_into_chunks(text)

        # All chunks must be < 16KB
        for chunk in result:
            assert _byte_length(chunk) < DEFAULT_CHUNK_MAX_BYTES

        # Should have created multiple chunks
        assert len(result) > 1

        # Verify all content is preserved (approximately)
        total_chars = sum(len(c) for c in result)
        # Account for paragraph separators being removed/changed
        assert total_chars > len(text) * 0.9
