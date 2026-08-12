from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


MODULE_PATH = Path(__file__).with_name("doc_index.py")


def load_module():
    if not MODULE_PATH.exists():
        pytest.fail("doc_index.py does not exist yet")
    spec = importlib.util.spec_from_file_location("doc_index", MODULE_PATH)
    if spec is None or spec.loader is None:
        pytest.fail("doc_index.py could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules["doc_index"] = module
    spec.loader.exec_module(module)
    return module


def require_function(name: str):
    module = load_module()
    function = getattr(module, name, None)
    if not callable(function):
        pytest.fail(f"{name} is not implemented yet")
    return function


def test_discover_markdown_uses_explicit_docs_glob(tmp_path: Path):
    (tmp_path / "docs" / "nested").mkdir(parents=True)
    (tmp_path / "docs" / "a.md").write_text("A", encoding="utf-8")
    (tmp_path / "docs" / "nested" / "b.md").write_text("B", encoding="utf-8")
    (tmp_path / "docs" / "ignore.txt").write_text("x", encoding="utf-8")
    (tmp_path / "README.md").write_text("root", encoding="utf-8")

    discover_markdown = require_function("discover_markdown")
    discovered = discover_markdown(tmp_path, ["docs/**/*.md"])

    assert [path.relative_to(tmp_path).as_posix() for path in discovered] == [
        "docs/a.md",
        "docs/nested/b.md",
    ]


def test_chunk_markdown_preserves_heading_context():
    chunk_markdown = require_function("chunk_markdown")
    markdown = "# Title\n\nIntro paragraph.\n\n## Section\n\nFirst.\n\nSecond.\n"

    chunks = chunk_markdown(markdown)

    assert chunks == [
        ("Title", "Intro paragraph."),
        ("Title > Section", "First.\n\nSecond."),
    ]


def test_chunk_markdown_keeps_fenced_code_intact():
    chunk_markdown = require_function("chunk_markdown")
    fenced = "```rust\nfn main() {\n    println!(\"hello\");\n}\n```"
    markdown = f"# Code\n\nBefore.\n\n{fenced}\n\nAfter.\n"

    chunks = chunk_markdown(markdown, max_chars=200, overlap_chars=20)

    assert chunks == [("Code", f"Before.\n\n{fenced}\n\nAfter.")]
    assert fenced in chunks[0][1]


def test_chunk_markdown_splits_oversized_section_with_overlap():
    chunk_markdown = require_function("chunk_markdown")
    paragraph_a = "alpha " * 12
    paragraph_b = "beta " * 12
    paragraph_c = "gamma " * 12
    markdown = f"# Long\n\n{paragraph_a}\n\n{paragraph_b}\n\n{paragraph_c}\n"

    chunks = chunk_markdown(markdown, max_chars=100, overlap_chars=20)

    assert len(chunks) >= 2
    assert all(heading == "Long" for heading, _ in chunks)
    assert all(len(text) <= 100 for _, text in chunks)
    assert any(first[-20:].strip() in second for (_, first), (_, second) in zip(chunks, chunks[1:]))
