"""Pytest configuration and fixtures."""

import pytest
from pathlib import Path


@pytest.fixture
def sample_chinese_text() -> str:
    """Sample Chinese text with multiple paragraphs and character names."""
    return """第一章

张三走进了房间。他看到李四正在看书。

"你好，李四，"张三说道。"今天天气真好。"

李四抬起头来。"是啊，张三。要不要一起去公园？"

第二章

王五和赵六也来了。他们是张三的老朋友。

"好久不见！"王五热情地打招呼。

赵六微笑着点点头。"我们一起去吃饭吧。"

大家都同意了张三的提议，一起出发了。"""


@pytest.fixture
def sample_english_text() -> str:
    """Sample English text with character names."""
    return """Chapter One

Alice walked into the room. She saw Bob reading a book.

"Hello, Bob," Alice said. "Nice weather today."

Bob looked up. "Indeed, Alice. Want to go to the park?"

Chapter Two

Charlie and Diana also arrived. They were old friends of Alice.

"Long time no see!" Charlie greeted warmly.

Diana smiled and nodded. "Let's go eat together."

Everyone agreed to Alice's suggestion and left together."""


@pytest.fixture
def temp_text_file(tmp_path: Path, sample_chinese_text: str) -> Path:
    """Create a temporary text file with sample content."""
    file_path = tmp_path / "sample.txt"
    file_path.write_text(sample_chinese_text, encoding="utf-8")
    return file_path


@pytest.fixture
def large_text() -> str:
    """Generate a large text for chunking tests."""
    paragraph = "这是一个测试段落，包含一些文字内容。张三和李四在讨论问题。" * 20
    paragraphs = [paragraph for _ in range(50)]
    return "\n\n".join(paragraphs)
