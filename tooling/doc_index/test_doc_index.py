from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import subprocess
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


def run_git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def make_git_repo(path: Path) -> None:
    path.mkdir(parents=True)
    run_git(path, "init")
    run_git(path, "config", "user.email", "doc-index@example.invalid")
    run_git(path, "config", "user.name", "Doc Index Tests")


def commit_all(path: Path, message: str = "fixture") -> str:
    run_git(path, "add", ".")
    run_git(path, "commit", "-m", message)
    return run_git(path, "rev-parse", "HEAD")


def test_read_git_state_tracks_clean_and_dirty_repository(tmp_path: Path):
    read_git_state = require_function("read_git_state")
    repo = tmp_path / "repo"
    make_git_repo(repo)
    (repo / "docs").mkdir()
    (repo / "docs" / "a.md").write_text("# A\n\nAlpha", encoding="utf-8")
    commit = commit_all(repo)

    clean = read_git_state("zed", repo)
    assert clean.name == "zed"
    assert clean.path == repo
    assert clean.commit == commit
    assert clean.dirty is False

    (repo / "docs" / "a.md").write_text("# A\n\nChanged", encoding="utf-8")
    dirty = read_git_state("zed", repo)
    assert dirty.commit == commit
    assert dirty.dirty is True


def test_collect_chunks_deduplicates_text_and_aggregates_sources(tmp_path: Path):
    module = load_module()
    collect_chunks = require_function("collect_chunks")
    shared = "# Shared\n\nSame semantic paragraph.\n"
    repositories = []

    for name in ("glass", "zed"):
        repo = tmp_path / name
        make_git_repo(repo)
        (repo / "docs").mkdir()
        (repo / "docs" / "shared.md").write_text(shared, encoding="utf-8")
        commit = commit_all(repo)
        repositories.append(module.SourceRepo(name, repo, commit, False))

    records = collect_chunks(repositories, ["docs/**/*.md"])
    assert len(records) == 1
    record = records[0]
    assert record.text == "Same semantic paragraph."
    assert record.content_hash == hashlib.sha256(record.text.encode("utf-8")).hexdigest()
    assert [location.repo for location in record.locations] == ["glass", "zed"]
    assert [location.relative_path for location in record.locations] == [
        "docs/shared.md",
        "docs/shared.md",
    ]
    assert all(location.heading == "Shared" for location in record.locations)
    assert all(location.chunk_index == 0 for location in record.locations)


def test_collect_chunks_order_is_deterministic(tmp_path: Path):
    module = load_module()
    collect_chunks = require_function("collect_chunks")
    repo = tmp_path / "repo"
    make_git_repo(repo)
    (repo / "docs").mkdir()
    (repo / "docs" / "z.md").write_text("# Z\n\nZulu", encoding="utf-8")
    (repo / "docs" / "a.md").write_text("# A\n\nAlpha", encoding="utf-8")
    commit = commit_all(repo)
    source = module.SourceRepo("zed", repo, commit, False)

    first = collect_chunks([source], ["docs/**/*.md"])
    second = collect_chunks([source], ["docs/**/*.md"])

    assert [(r.content_hash, r.text) for r in first] == [(r.content_hash, r.text) for r in second]
    assert [r.text for r in first] == ["Alpha", "Zulu"]
