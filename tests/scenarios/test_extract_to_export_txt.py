"""Scenario test: TXT extract -> edit -> replace/export flow."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from txt_process.core import api
from txt_process.core.document import TextDocument


def test_txt_extract_to_export_flow(
    txt_story_path: Path,
    scenario_config,
    fake_llm_client,
):
    document = api.load_document(txt_story_path)
    assert isinstance(document, TextDocument)

    llm_calls = fake_llm_client(["张三", "张三丰", "Alice"])
    with patch("txt_process.core.extraction.split_into_chunks", return_value=[document.text]):
        extraction = api.extract_names(document.text, scenario_config, api_key="ollama")

    assert llm_calls == [document.text]
    assert [name for name, _ in extraction.name_pairs] == ["张三", "张三丰", "Alice"]

    mappings = {
        "张三": "李四",
        "张三丰": "无忌",
        "Alice": "Bob",
    }
    replace_result = api.replace_and_export(document, mappings)
    output_text = replace_result.output_path.read_text(encoding="utf-8")

    assert replace_result.output_path.name == "story_processed.txt"
    assert "李四和无忌在聊天" in output_text
    assert "Bob的故事" in output_text
    assert "Bob met Bob." in output_text
    assert "Bob123 stays." in output_text
    assert replace_result.totals["张三"] == 1
    assert replace_result.totals["张三丰"] == 1
    assert replace_result.totals["Alice"] == 3
