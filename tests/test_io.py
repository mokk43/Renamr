"""Tests for file I/O."""

import pytest
from pathlib import Path

from txt_process.core.io import load_text_file, save_text_file


class TestLoadTextFile:
    """Tests for text file loading."""

    def test_load_utf8_file(self, tmp_path: Path):
        """Load a UTF-8 encoded file."""
        test_file = tmp_path / "test.txt"
        content = "Hello, World!\n你好，世界！"
        test_file.write_text(content, encoding="utf-8")

        result, encoding = load_text_file(test_file)
        assert result == content
        assert encoding == "utf-8"

    def test_load_utf8_bom_file(self, tmp_path: Path):
        """Load a UTF-8 with BOM file."""
        test_file = tmp_path / "test.txt"
        content = "Hello with BOM"
        # Write with BOM
        test_file.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))

        result, encoding = load_text_file(test_file)
        assert result == content
        assert encoding == "utf-8-sig"

    def test_load_gb18030_file(self, tmp_path: Path):
        """Load a GB18030 encoded file."""
        test_file = tmp_path / "test.txt"
        content = "中文内容测试"
        test_file.write_bytes(content.encode("gb18030"))

        result, encoding = load_text_file(test_file)
        assert "中文" in result
        # Encoding could be gb18030 or gbk (both work for this content)
        assert encoding in ("gb18030", "gbk", "utf-8")

    def test_file_not_found(self, tmp_path: Path):
        """FileNotFoundError for missing file."""
        missing = tmp_path / "missing.txt"
        with pytest.raises(FileNotFoundError):
            load_text_file(missing)

    def test_empty_file(self, tmp_path: Path):
        """Empty file returns empty string."""
        test_file = tmp_path / "empty.txt"
        test_file.write_text("")

        result, encoding = load_text_file(test_file)
        assert result == ""


class TestSaveTextFile:
    """Tests for text file saving."""

    def test_save_utf8(self, tmp_path: Path):
        """Save as UTF-8."""
        test_file = tmp_path / "output.txt"
        content = "Test content\n测试内容"

        save_text_file(test_file, content)

        # Read back and verify
        saved = test_file.read_text(encoding="utf-8")
        assert saved == content

    def test_save_with_encoding(self, tmp_path: Path):
        """Save with specified encoding."""
        test_file = tmp_path / "output.txt"
        content = "Test"

        save_text_file(test_file, content, encoding="utf-8-sig")

        # Read back raw bytes and check for BOM
        raw = test_file.read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf")

    def test_overwrite_existing(self, tmp_path: Path):
        """Overwrite an existing file."""
        test_file = tmp_path / "output.txt"
        test_file.write_text("old content")

        save_text_file(test_file, "new content")

        assert test_file.read_text() == "new content"
