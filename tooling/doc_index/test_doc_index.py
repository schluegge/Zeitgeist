from __future__ import annotations

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading

import numpy as np
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


def start_embed_server(response_body: bytes, status: int = 200):
    requests: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            requests.append({"path": self.path, "json": json.loads(body)})
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(response_body)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, requests


def require_type(name: str):
    module = load_module()
    value = getattr(module, name, None)
    if not isinstance(value, type):
        pytest.fail(f"{name} is not implemented yet")
    return value


def test_ollama_embedder_batches_and_normalizes_float32_vectors():
    response = json.dumps({"embeddings": [[3.0, 4.0], [0.0, 2.0]]}).encode()
    server, requests = start_embed_server(response)
    try:
        embedder_type = require_type("OllamaEmbedder")
        embedder = embedder_type(base_url=f"http://127.0.0.1:{server.server_port}", model="bge-m3")
        vectors = embedder.embed(["first", "second"])
    finally:
        server.shutdown()
        server.server_close()

    assert vectors.dtype == np.float32
    assert vectors.shape == (2, 2)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0)
    assert requests == [{
        "path": "/api/embed",
        "json": {"model": "bge-m3", "input": ["first", "second"], "truncate": False},
    }]


def test_ollama_embedder_rejects_mismatched_vector_dimensions():
    response = json.dumps({"embeddings": [[1.0, 2.0], [1.0, 2.0, 3.0]]}).encode()
    server, _ = start_embed_server(response)
    try:
        embedder = require_type("OllamaEmbedder")(base_url=f"http://127.0.0.1:{server.server_port}")
        with pytest.raises(RuntimeError, match="dimension"):
            embedder.embed(["first", "second"])
    finally:
        server.shutdown()
        server.server_close()


def test_ollama_embedder_rejects_malformed_json():
    server, _ = start_embed_server(b"not-json")
    try:
        embedder = require_type("OllamaEmbedder")(base_url=f"http://127.0.0.1:{server.server_port}")
        with pytest.raises(RuntimeError, match="JSON"):
            embedder.embed(["text"])
    finally:
        server.shutdown()
        server.server_close()


def test_ollama_embedder_reports_unavailable_endpoint():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    embedder = require_type("OllamaEmbedder")(base_url=f"http://127.0.0.1:{port}")

    with pytest.raises(RuntimeError, match="Ollama"):
        embedder.embed(["text"])


def make_persistence_fixture(module, text: str = "Alpha"):
    location = module.ChunkLocation(
        repo="zed",
        commit="a" * 40,
        dirty=False,
        relative_path="docs/a.md",
        chunk_index=0,
        heading="A",
    )
    chunk = module.ChunkRecord(
        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        text=text,
        locations=[location],
    )
    manifest = module.IndexManifest(
        schema_version=1,
        model="bge-m3",
        vector_dimension=2,
        chunk_count=1,
        built_at="2026-08-13T00:00:00+00:00",
        repositories=[{"name": "zed", "path": "C:/zed", "commit": "a" * 40, "dirty": False}],
        include_globs=["docs/**/*.md"],
    )
    vectors = np.asarray([[1.0, 0.0]], dtype=np.float32)
    return manifest, [chunk], vectors


def test_persistence_round_trip(tmp_path: Path):
    module = load_module()
    if not hasattr(module, "IndexManifest"):
        pytest.fail("IndexManifest is not implemented yet")
    write_index = getattr(module, "write_index", None)
    load_index = getattr(module, "load_index", None)
    if not callable(write_index) or not callable(load_index):
        pytest.fail("write_index/load_index are not implemented yet")
    manifest, chunks, vectors = make_persistence_fixture(module)
    index_dir = tmp_path / "index"

    write_index(index_dir, manifest, chunks, vectors)
    loaded_manifest, loaded_chunks, loaded_vectors = load_index(index_dir)

    assert loaded_manifest == manifest
    assert loaded_chunks == chunks
    assert loaded_vectors.dtype == np.float32
    assert np.array_equal(loaded_vectors, vectors)


def test_write_index_rejects_row_mismatch(tmp_path: Path):
    module = load_module()
    write_index = getattr(module, "write_index", None)
    if not callable(write_index) or not hasattr(module, "IndexManifest"):
        pytest.fail("persistence is not implemented yet")
    manifest, chunks, _ = make_persistence_fixture(module)
    bad_vectors = np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    with pytest.raises(ValueError, match="row"):
        write_index(tmp_path / "index", manifest, chunks, bad_vectors)


def test_load_index_rejects_schema_and_model_mismatch(tmp_path: Path):
    module = load_module()
    if not hasattr(module, "IndexManifest"):
        pytest.fail("IndexManifest is not implemented yet")
    write_index = getattr(module, "write_index", None)
    load_index = getattr(module, "load_index", None)
    if not callable(write_index) or not callable(load_index):
        pytest.fail("persistence is not implemented yet")
    manifest, chunks, vectors = make_persistence_fixture(module)
    index_dir = tmp_path / "index"
    write_index(index_dir, manifest, chunks, vectors)

    manifest_path = index_dir / "manifest.json"
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["schema_version"] = 999
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RuntimeError, match="schema"):
        load_index(index_dir)

    raw["schema_version"] = 1
    raw["model"] = "other-model"
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RuntimeError, match="model"):
        load_index(index_dir)


def test_load_index_rejects_corrupted_jsonl(tmp_path: Path):
    module = load_module()
    if not hasattr(module, "IndexManifest"):
        pytest.fail("IndexManifest is not implemented yet")
    write_index = getattr(module, "write_index", None)
    load_index = getattr(module, "load_index", None)
    if not callable(write_index) or not callable(load_index):
        pytest.fail("persistence is not implemented yet")
    manifest, chunks, vectors = make_persistence_fixture(module)
    index_dir = tmp_path / "index"
    write_index(index_dir, manifest, chunks, vectors)
    (index_dir / "chunks.jsonl").write_text("{broken\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="chunks"):
        load_index(index_dir)


def test_failed_staged_write_preserves_previous_index(tmp_path: Path, monkeypatch):
    module = load_module()
    if not hasattr(module, "IndexManifest"):
        pytest.fail("IndexManifest is not implemented yet")
    write_index = getattr(module, "write_index", None)
    load_index = getattr(module, "load_index", None)
    if not callable(write_index) or not callable(load_index):
        pytest.fail("persistence is not implemented yet")
    manifest, chunks, vectors = make_persistence_fixture(module, "Old")
    index_dir = tmp_path / "index"
    write_index(index_dir, manifest, chunks, vectors)

    def fail_save(*args, **kwargs):
        raise OSError("simulated write failure")

    monkeypatch.setattr(module.np, "save", fail_save)
    new_manifest, new_chunks, new_vectors = make_persistence_fixture(module, "New")
    with pytest.raises(OSError, match="simulated"):
        write_index(index_dir, new_manifest, new_chunks, new_vectors)

    loaded_manifest, loaded_chunks, loaded_vectors = load_index(index_dir)
    assert loaded_chunks[0].text == "Old"
    assert loaded_manifest.chunk_count == 1
    assert np.array_equal(loaded_vectors, vectors)


class FakeEmbedder:
    model = "bge-m3"

    def embed(self, texts):
        rows = []
        for index, _text in enumerate(texts):
            rows.append([1.0, 0.0] if index % 2 == 0 else [0.0, 1.0])
        return np.asarray(rows, dtype=np.float32)


def make_documented_repo(path: Path, files: dict[str, str]) -> str:
    make_git_repo(path)
    for relative_path, content in files.items():
        target = path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return commit_all(path)


def test_build_index_uses_docs_glob_and_preserves_source_bytes(tmp_path: Path):
    module = load_module()
    build_index = getattr(module, "build_index", None)
    if not callable(build_index):
        pytest.fail("build_index is not implemented yet")
    repo = tmp_path / "repo"
    make_documented_repo(repo, {
        "docs/a.md": "# Alpha\n\nDocumentation body.",
        "README.md": "# Root\n\nNot in default corpus.",
    })
    before = {
        path.relative_to(repo).as_posix(): path.read_bytes()
        for path in repo.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }
    index_dir = tmp_path / "index"

    manifest = build_index([f"zed={repo}"], [], index_dir, FakeEmbedder())
    loaded_manifest, chunks, _vectors = module.load_index(index_dir)

    assert manifest.chunk_count == 1
    assert loaded_manifest.include_globs == ["docs/**/*.md"]
    assert [chunk.text for chunk in chunks] == ["Documentation body."]
    after = {
        path.relative_to(repo).as_posix(): path.read_bytes()
        for path in repo.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }
    assert after == before


def test_build_index_additional_include_extends_default_corpus(tmp_path: Path):
    module = load_module()
    build_index = getattr(module, "build_index", None)
    if not callable(build_index):
        pytest.fail("build_index is not implemented yet")
    repo = tmp_path / "repo"
    make_documented_repo(repo, {
        "docs/a.md": "# A\n\nAlpha",
        "notes/b.md": "# B\n\nBeta",
    })
    index_dir = tmp_path / "index"
    manifest = build_index(
        [f"zed={repo}"], ["notes/**/*.md"], index_dir, FakeEmbedder()
    )
    _loaded_manifest, chunks, _vectors = module.load_index(index_dir)

    assert manifest.chunk_count == 2
    assert manifest.include_globs == ["docs/**/*.md", "notes/**/*.md"]
    assert [chunk.text for chunk in chunks] == ["Alpha", "Beta"]


@pytest.mark.parametrize(
    "repo_specs",
    [
        ["missing-equals"],
        ["=C:/missing"],
        ["zed="],
    ],
)
def test_build_index_rejects_malformed_repo_specs(tmp_path: Path, repo_specs):
    build_index = getattr(load_module(), "build_index", None)
    if not callable(build_index):
        pytest.fail("build_index is not implemented yet")
    with pytest.raises(ValueError, match="NAME=PATH"):
        build_index(repo_specs, [], tmp_path / "index", FakeEmbedder())


def test_build_index_rejects_duplicate_repo_names(tmp_path: Path):
    module = load_module()
    build_index = getattr(module, "build_index", None)
    if not callable(build_index):
        pytest.fail("build_index is not implemented yet")
    first = tmp_path / "first"
    second = tmp_path / "second"
    make_documented_repo(first, {"docs/a.md": "# A\n\nAlpha"})
    make_documented_repo(second, {"docs/b.md": "# B\n\nBeta"})

    with pytest.raises(ValueError, match="duplicate"):
        build_index(
            [f"zed={first}", f"zed={second}"],
            [],
            tmp_path / "index",
            FakeEmbedder(),
        )


def test_build_index_rebuild_has_identical_chunk_mappings(tmp_path: Path):
    module = load_module()
    build_index = getattr(module, "build_index", None)
    if not callable(build_index):
        pytest.fail("build_index is not implemented yet")
    repo = tmp_path / "repo"
    make_documented_repo(repo, {
        "docs/a.md": "# A\n\nAlpha",
        "docs/b.md": "# B\n\nBeta",
    })
    first_dir = tmp_path / "first-index"
    second_dir = tmp_path / "second-index"
    build_index([f"zed={repo}"], [], first_dir, FakeEmbedder())
    build_index([f"zed={repo}"], [], second_dir, FakeEmbedder())
    _m1, first_chunks, _v1 = module.load_index(first_dir)
    _m2, second_chunks, _v2 = module.load_index(second_dir)

    first_mapping = [
        (chunk.content_hash, chunk.text, [vars(location) for location in chunk.locations])
        for chunk in first_chunks
    ]
    second_mapping = [
        (chunk.content_hash, chunk.text, [vars(location) for location in chunk.locations])
        for chunk in second_chunks
    ]
    assert first_mapping == second_mapping


def test_build_index_rejects_missing_and_non_git_paths(tmp_path: Path):
    build_index = getattr(load_module(), "build_index", None)
    if not callable(build_index):
        pytest.fail("build_index is not implemented yet")

    with pytest.raises(ValueError, match="does not exist"):
        build_index([f"zed={tmp_path / 'missing'}"], [], tmp_path / "index-a", FakeEmbedder())

    non_git = tmp_path / "not-git"
    non_git.mkdir()
    with pytest.raises(ValueError, match="Git"):
        build_index([f"zed={non_git}"], [], tmp_path / "index-b", FakeEmbedder())


class FixedQueryEmbedder:
    model = "bge-m3"

    def __init__(self, vector):
        self.vector = np.asarray(vector, dtype=np.float32)

    def embed(self, texts):
        assert len(texts) == 1
        vector = self.vector / np.linalg.norm(self.vector)
        return vector[np.newaxis, :].astype(np.float32)


def make_search_fixture(module, index_dir: Path):
    def location(repo: str, path: str):
        return module.ChunkLocation(
            repo=repo,
            commit=("a" if repo == "zed" else "b") * 40,
            dirty=False,
            relative_path=path,
            chunk_index=0,
            heading="Topic",
        )

    texts = ["Primary", "Secondary", "Orthogonal"]
    chunks = [
        module.ChunkRecord(hashlib.sha256(text.encode()).hexdigest(), text, [])
        for text in texts
    ]
    chunks[0].locations = [
        location("glass", "docs/shared.md"),
        location("zed", "docs/shared.md"),
    ]
    chunks[1].locations = [location("glass", "docs/secondary.md")]
    chunks[2].locations = [location("zed", "docs/orthogonal.md")]
    vectors = np.asarray(
        [[1.0, 0.0], [0.8, 0.6], [0.0, 1.0]], dtype=np.float32
    )
    manifest = module.IndexManifest(
        schema_version=1,
        model="bge-m3",
        vector_dimension=2,
        chunk_count=3,
        built_at="2026-08-13T00:00:00+00:00",
        repositories=[
            {"name": "glass", "path": "C:/glass", "commit": "b" * 40, "dirty": False},
            {"name": "zed", "path": "C:/zed", "commit": "a" * 40, "dirty": False},
        ],
        include_globs=["docs/**/*.md"],
    )
    module.write_index(index_dir, manifest, chunks, vectors)
    return chunks


def test_search_index_orders_by_cosine_and_respects_top_k(tmp_path: Path):
    module = load_module()
    search_index = getattr(module, "search_index", None)
    if not callable(search_index):
        pytest.fail("search_index is not implemented yet")
    index_dir = tmp_path / "index"
    make_search_fixture(module, index_dir)

    results = search_index(
        "closest topic",
        index_dir,
        FixedQueryEmbedder([1.0, 0.0]),
        [],
        2,
    )

    assert [result.chunk.text for result in results] == ["Primary", "Secondary"]
    assert results[0].score == pytest.approx(1.0)
    assert results[1].score == pytest.approx(0.8)


def test_search_index_filters_locations_by_repository(tmp_path: Path):
    module = load_module()
    search_index = getattr(module, "search_index", None)
    if not callable(search_index):
        pytest.fail("search_index is not implemented yet")
    index_dir = tmp_path / "index"
    make_search_fixture(module, index_dir)
    results = search_index(
        "closest topic",
        index_dir,
        FixedQueryEmbedder([1.0, 0.0]),
        ["zed"],
        10,
    )

    assert [result.chunk.text for result in results] == ["Primary", "Orthogonal"]
    assert [[location.repo for location in result.matched_locations] for result in results] == [
        ["zed"],
        ["zed"],
    ]


def test_search_index_rejects_unknown_repository_filter(tmp_path: Path):
    module = load_module()
    search_index = getattr(module, "search_index", None)
    if not callable(search_index):
        pytest.fail("search_index is not implemented yet")
    index_dir = tmp_path / "index"
    make_search_fixture(module, index_dir)

    with pytest.raises(ValueError, match="unknown repository"):
        search_index("topic", index_dir, FixedQueryEmbedder([1.0, 0.0]), ["missing"], 5)


def test_search_index_uses_stable_row_order_for_ties(tmp_path: Path):
    module = load_module()
    search_index = getattr(module, "search_index", None)
    if not callable(search_index):
        pytest.fail("search_index is not implemented yet")
    index_dir = tmp_path / "index"
    chunks = make_search_fixture(module, index_dir)
    manifest, _loaded_chunks, vectors = module.load_index(index_dir)
    vectors[1] = vectors[0]
    module.write_index(index_dir, manifest, chunks, vectors)

    results = search_index(
        "tie",
        index_dir,
        FixedQueryEmbedder([1.0, 0.0]),
        [],
        2,
    )

    assert [result.chunk.text for result in results] == ["Primary", "Secondary"]


class CliEmbedder:
    model = "bge-m3"

    def embed(self, texts):
        rows = []
        for index, _text in enumerate(texts):
            rows.append([1.0, 0.0] if index == 0 else [0.0, 1.0])
        return np.asarray(rows, dtype=np.float32)


def test_default_index_dir_uses_localappdata(monkeypatch, tmp_path: Path):
    module = load_module()
    default_index_dir = getattr(module, "default_index_dir", None)
    if not callable(default_index_dir):
        pytest.fail("default_index_dir is not implemented yet")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert default_index_dir() == tmp_path / "Zeitgeist" / "doc-index"


def test_cli_build_and_search_print_ranked_source_details(tmp_path: Path, monkeypatch, capsys):
    module = load_module()
    main = getattr(module, "main", None)
    if not callable(main):
        pytest.fail("main is not implemented yet")
    monkeypatch.setattr(module, "OllamaEmbedder", CliEmbedder)
    repo = tmp_path / "repo"
    commit = make_documented_repo(repo, {"docs/a.md": "# Alpha\n\nSemantic content."})
    index_dir = tmp_path / "index"

    build_code = main([
        "build",
        "--repo", f"zed={repo}",
        "--index-dir", str(index_dir),
    ])
    build_output = capsys.readouterr()
    assert build_code == 0
    assert "Built 1 unique chunks" in build_output.out

    search_code = main([
        "search",
        "semantic topic",
        "--index-dir", str(index_dir),
        "--top-k", "1",
    ])
    search_output = capsys.readouterr()
    assert search_code == 0
    assert "1.0000" in search_output.out
    assert f"zed@{commit[:10]}" in search_output.out
    assert "docs/a.md" in search_output.out
    assert "Alpha" in search_output.out
    assert "Semantic content." in search_output.out


def test_cli_rejects_non_positive_top_k(tmp_path: Path, monkeypatch, capsys):
    module = load_module()
    main = getattr(module, "main", None)
    if not callable(main):
        pytest.fail("main is not implemented yet")
    monkeypatch.setattr(module, "OllamaEmbedder", CliEmbedder)

    code = main(["search", "query", "--index-dir", str(tmp_path / "missing"), "--top-k", "0"])
    output = capsys.readouterr()

    assert code != 0
    assert "top-k" in output.err.lower()


def test_cli_search_warns_when_indexed_repo_state_is_stale(tmp_path: Path, monkeypatch, capsys):
    module = load_module()
    main = getattr(module, "main", None)
    if not callable(main):
        pytest.fail("main is not implemented yet")
    monkeypatch.setattr(module, "OllamaEmbedder", CliEmbedder)
    repo = tmp_path / "repo"
    make_documented_repo(repo, {"docs/a.md": "# Alpha\n\nSemantic content."})
    index_dir = tmp_path / "index"
    assert main(["build", "--repo", f"zed={repo}", "--index-dir", str(index_dir)]) == 0
    capsys.readouterr()
    (repo / "docs" / "a.md").write_text(
        "# Alpha\n\nChanged after indexing.", encoding="utf-8"
    )

    code = main(["search", "semantic", "--index-dir", str(index_dir)])
    output = capsys.readouterr()

    assert code == 0
    assert "WARNING" in output.err
    assert "stale" in output.err.lower()
    assert "zed" in output.err


def test_console_entrypoint_is_installed_in_uv_project():
    project_dir = MODULE_PATH.parent
    completed = subprocess.run(
        ["uv", "run", "--project", str(project_dir), "zeitgeist-doc-index", "--help"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "build" in completed.stdout
    assert "search" in completed.stdout


def test_collect_chunks_strips_utf8_bom(tmp_path: Path):
    module = load_module()
    repo = tmp_path / "repo"
    make_git_repo(repo)
    (repo / "docs").mkdir()
    (repo / "docs" / "bom.md").write_bytes(
        b"\xef\xbb\xbf# Title\n\nBody text.\n"
    )
    commit = commit_all(repo)
    source = module.SourceRepo("zed", repo, commit, False)

    records = module.collect_chunks([source], ["docs/**/*.md"])

    assert len(records) == 1
    assert records[0].text == "Body text."
    assert records[0].locations[0].heading == "Title"


def test_chunk_markdown_splits_oversized_fence_into_balanced_fences():
    module = load_module()
    body_lines = [f'"key{i}": "{'x' * 18}"' for i in range(8)]
    fenced = "```json [settings]\n" + "\n".join(body_lines) + "\n```"
    markdown = f"# Code\n\n{fenced}\n"

    chunks = module.chunk_markdown(markdown, max_chars=100, overlap_chars=20)

    assert len(chunks) > 1
    assert all(len(text) <= 100 for _heading, text in chunks)
    assert all(text.startswith("```json [settings]\n") for _heading, text in chunks)
    assert all(text.endswith("\n```") for _heading, text in chunks)
    recovered_lines = []
    for _heading, text in chunks:
        recovered_lines.extend(text.splitlines()[1:-1])
    assert recovered_lines == body_lines


def test_ollama_embedder_splits_inputs_into_bounded_batches():
    response = json.dumps({"embeddings": [[3.0, 4.0], [0.0, 2.0]]}).encode()
    server, requests = start_embed_server(response)
    try:
        embedder = require_type("OllamaEmbedder")(
            base_url=f"http://127.0.0.1:{server.server_port}",
            model="bge-m3",
            batch_size=2,
        )
        vectors = embedder.embed(["one", "two", "three", "four"])
    finally:
        server.shutdown()
        server.server_close()

    assert vectors.shape == (4, 2)
    assert [request["json"]["input"] for request in requests] == [
        ["one", "two"],
        ["three", "four"],
    ]


def test_ollama_embedder_defaults_to_128_input_batches():
    response = json.dumps({"embeddings": [[1.0, 0.0]] * 128}).encode()
    server, requests = start_embed_server(response)
    try:
        embedder = require_type("OllamaEmbedder")(
            base_url=f"http://127.0.0.1:{server.server_port}",
            model="bge-m3",
        )
        vectors = embedder.embed([f"text-{index}" for index in range(256)])
    finally:
        server.shutdown()
        server.server_close()

    assert vectors.shape == (256, 2)
    assert [len(request["json"]["input"]) for request in requests] == [128, 128]


def test_console_configuration_forces_utf8_under_cp1252_environment():
    script = (
        "import doc_index; "
        "doc_index._configure_console_streams(); "
        "print('done ' + chr(0x2713))"
    )
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "cp1252"
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=MODULE_PATH.parent,
        env=environment,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.rstrip(b"\r\n") == ("done " + chr(0x2713)).encode("utf-8")


def test_configure_console_streams_forces_utf8(monkeypatch):
    module = load_module()

    class FakeStream:
        def __init__(self):
            self.calls = []
        def reconfigure(self, **kwargs):
            self.calls.append(kwargs)

    stdout = FakeStream()
    stderr = FakeStream()
    monkeypatch.setattr(module.sys, "stdout", stdout)
    monkeypatch.setattr(module.sys, "stderr", stderr)

    module._configure_console_streams()

    assert stdout.calls == [{"encoding": "utf-8", "errors": "replace"}]
    assert stderr.calls == [{"encoding": "utf-8", "errors": "replace"}]

def test_excerpt_uses_unicode_ellipsis_without_mojibake():
    module = load_module()
    excerpt = module._excerpt("x" * 300, limit=12)
    assert excerpt == "x" * 11 + chr(0x2026)
