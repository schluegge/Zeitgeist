# Documentation Vector Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a persistent local semantic index for Zed, Glass, and Zeitgeist Markdown documentation, backed by local Ollama `bge-m3` embeddings and deterministic NumPy cosine search.

**Architecture:** Add an isolated Python tool under `tooling/doc_index/` with no dependency on the Rust workspace. The tool scans explicitly supplied Git repositories, chunks Markdown deterministically, deduplicates chunk text by SHA-256 while aggregating source locations, embeds batches through Ollama `/api/embed`, atomically persists `manifest.json`, `chunks.jsonl`, and `vectors.npy`, then supports validated cosine search with optional repository filtering.

**Tech Stack:** Python 3.13+, `numpy`, Python standard library (`argparse`, `hashlib`, `json`, `pathlib`, `subprocess`, `urllib`), `pytest`, local Ollama HTTP API.

## Global Constraints

- Index Markdown documentation only in v1; source code remains outside the vector index.
- Default corpus per repository is `docs/**/*.md`; explicit additional Markdown globs are allowed.
- Chunk by heading and paragraph boundaries, preserve fenced code blocks, cap chunks at 3,500 characters, and use at most 300 characters of overlap when splitting oversized sections.
- Use local Ollama model `bge-m3`; do not add a hosted embedding provider.
- Persist normalized `float32` embeddings as `vectors.npy`; store row-aligned metadata in `chunks.jsonl` and schema/configuration/state in `manifest.json`.
- Deduplicate identical chunk content by SHA-256 and retain every source location for a duplicate chunk.
- Build atomically through a temporary sibling directory; failed builds must not corrupt the last valid index.
- Default index location is `%LOCALAPPDATA%\Zeitgeist\doc-index`.
- Do not mutate source repositories or documentation during indexing.
- No FAISS, Qdrant, watcher daemon, or background rebuild service.

---
## File Structure

- Create `tooling/doc_index/pyproject.toml`: isolated Python environment, console entry point, NumPy runtime dependency, pytest dev dependency.
- Create `tooling/doc_index/doc_index.py`: data models, Git metadata collection, Markdown discovery/chunking, deduplication, Ollama client, persistence validation, build/search commands, CLI.
- Create `tooling/doc_index/test_doc_index.py`: deterministic unit and integration tests, including an in-process fake Ollama HTTP server.
- Create `tooling/doc_index/README.md`: concise build/search usage and real-model smoke-test commands.

### Task 1: Markdown discovery and deterministic chunking

**Files:**
- Create: `tooling/doc_index/pyproject.toml`
- Create: `tooling/doc_index/doc_index.py`
- Create: `tooling/doc_index/test_doc_index.py`

**Interfaces:**
- Produces: `SourceRepo(name: str, path: Path, commit: str, dirty: bool)`.
- Produces: `ChunkLocation(repo: str, commit: str, dirty: bool, relative_path: str, chunk_index: int, heading: str)`.
- Produces: `ChunkRecord(content_hash: str, text: str, locations: list[ChunkLocation])`.
- Produces: `discover_markdown(repo_path: Path, include_globs: Sequence[str]) -> list[Path]`.
- Produces: `chunk_markdown(text: str, max_chars: int = 3500, overlap_chars: int = 300) -> list[tuple[str, str]]`, returning `(heading, text)` pairs.

- [ ] **Step 1: Write failing tests for default discovery, heading context, fenced code preservation, and oversized overlap.**
- [ ] **Step 2: Run `uv run --project tooling/doc_index pytest tooling/doc_index/test_doc_index.py -k 'discover or chunk' -v` and verify failures are caused by missing production functions.**
- [ ] **Step 3: Implement the minimal dataclasses, Markdown discovery, and deterministic chunker.**
- [ ] **Step 4: Re-run the focused tests and verify they pass.**
- [ ] **Step 5: Commit with `git commit -m "Add deterministic documentation chunking"`.**
### Task 2: Git provenance and SHA-256 deduplication

**Files:**
- Modify: `tooling/doc_index/doc_index.py`
- Modify: `tooling/doc_index/test_doc_index.py`

**Interfaces:**
- Consumes: `SourceRepo`, `ChunkLocation`, `ChunkRecord`, `discover_markdown`, `chunk_markdown`.
- Produces: `read_git_state(name: str, repo_path: Path) -> SourceRepo`.
- Produces: `collect_chunks(repositories: Sequence[SourceRepo], include_globs: Sequence[str]) -> list[ChunkRecord]`.
- `collect_chunks` sorts repositories, paths, and chunk order deterministically before hashing and aggregation.

- [ ] **Step 1: Write failing tests proving clean/dirty Git state capture, stable SHA-256 hashes, duplicate-source aggregation, and deterministic ordering.**
- [ ] **Step 2: Run the focused provenance/deduplication tests and verify the expected failures.**
- [ ] **Step 3: Implement Git state reads with `git -C`, content hashing, source aggregation, and deterministic sorting.**
- [ ] **Step 4: Run focused tests plus all Task 1 tests and verify they pass.**
- [ ] **Step 5: Commit with `git commit -m "Track documentation source provenance"`.**

### Task 3: Ollama embedding client and vector normalization

**Files:**
- Modify: `tooling/doc_index/doc_index.py`
- Modify: `tooling/doc_index/test_doc_index.py`

**Interfaces:**
- Produces: `OllamaEmbedder(base_url: str = "http://localhost:11434", model: str = "bge-m3")`.
- Produces: `OllamaEmbedder.embed(texts: Sequence[str]) -> np.ndarray` with shape `(n, dimension)` and dtype `float32`.
- Embedding requests use `POST /api/embed` with JSON `{model, input, truncate: false}` and validate response count, finite values, nonzero dimensions, and consistent width.

- [ ] **Step 1: Write a fake local HTTP server and failing tests for batching, model payload, normalized `float32` output, unavailable endpoint, malformed JSON, and dimension mismatch.**
- [ ] **Step 2: Run `pytest -k embed -v` through the project environment and verify failures precede implementation.**
- [ ] **Step 3: Implement the standard-library HTTP client, explicit error messages, response validation, and defensive L2 normalization.**
- [ ] **Step 4: Re-run embedding tests and the full suite.**
- [ ] **Step 5: Commit with `git commit -m "Add local Ollama embedding client"`.**
### Task 4: Atomic persistence and index validation

**Files:**
- Modify: `tooling/doc_index/doc_index.py`
- Modify: `tooling/doc_index/test_doc_index.py`

**Interfaces:**
- Produces: `IndexManifest(schema_version: int, model: str, vector_dimension: int, chunk_count: int, built_at: str, repositories: list[dict], include_globs: list[str])`.
- Produces: `write_index(index_dir: Path, manifest: IndexManifest, chunks: Sequence[ChunkRecord], vectors: np.ndarray) -> None`.
- Produces: `load_index(index_dir: Path, expected_model: str = "bge-m3") -> tuple[IndexManifest, list[ChunkRecord], np.ndarray]`.
- `write_index` validates row alignment and finite normalized vectors before replacing the active directory.

- [ ] **Step 1: Write failing tests for round-trip persistence, row-alignment rejection, schema/model mismatch, corrupted JSONL, and preservation of an existing index when a staged write fails.**
- [ ] **Step 2: Run `pytest -k 'persist or load_index or atomic' -v` and verify expected failures.**
- [ ] **Step 3: Implement JSON serialization, NumPy persistence, validation, sibling staging directory creation, backup/replace logic, and cleanup on error.**
- [ ] **Step 4: Run focused tests and the complete suite.**
- [ ] **Step 5: Commit with `git commit -m "Persist documentation index atomically"`.**

### Task 5: Build orchestration and deterministic rebuild

**Files:**
- Modify: `tooling/doc_index/doc_index.py`
- Modify: `tooling/doc_index/test_doc_index.py`

**Interfaces:**
- Produces: `build_index(repo_specs: Sequence[str], include_globs: Sequence[str], index_dir: Path, embedder: OllamaEmbedder) -> IndexManifest`.
- Repo specs use exact `NAME=PATH` parsing and reject duplicate names, missing paths, non-Git directories, and names without paths.
- Build embeds only unique chunk text and writes source Git state into the manifest and every location.

- [ ] **Step 1: Write failing integration tests using temporary Git repositories and the fake embedder for default `docs/**/*.md`, extra includes, invalid repo specs, deterministic chunk/source mappings, and no mutation of source files.**
- [ ] **Step 2: Run `pytest -k build_index -v` and verify failures.**
- [ ] **Step 3: Implement repository parsing and the complete build pipeline from discovery through atomic persistence.**
- [ ] **Step 4: Re-run focused and full tests, then compare two rebuilds for identical hashes/source mappings.**
- [ ] **Step 5: Commit with `git commit -m "Build persistent documentation vector index"`.**
### Task 6: Semantic search and repository filtering

**Files:**
- Modify: `tooling/doc_index/doc_index.py`
- Modify: `tooling/doc_index/test_doc_index.py`

**Interfaces:**
- Produces: `SearchResult(score: float, chunk: ChunkRecord, matched_locations: list[ChunkLocation])`.
- Produces: `search_index(query: str, index_dir: Path, embedder: OllamaEmbedder, repo_filters: Sequence[str], top_k: int) -> list[SearchResult]`.
- Ranking computes `vectors @ normalized_query`; repository filters operate on source locations and exclude chunks with no matching location.

- [ ] **Step 1: Write failing tests with fixed vectors for cosine ordering, ties, `top_k`, repo filtering, unknown repo filters, and duplicate chunks whose locations span multiple repositories.**
- [ ] **Step 2: Run `pytest -k search -v` and verify failures.**
- [ ] **Step 3: Implement query embedding, filtering, matrix-vector ranking, stable tie ordering, and result projection.**
- [ ] **Step 4: Run focused tests and the complete suite.**
- [ ] **Step 5: Commit with `git commit -m "Search documentation vectors semantically"`.**

### Task 7: CLI, stale-state reporting, and operator documentation

**Files:**
- Modify: `tooling/doc_index/doc_index.py`
- Modify: `tooling/doc_index/test_doc_index.py`
- Create: `tooling/doc_index/README.md`

**Interfaces:**
- Produces: `main(argv: Sequence[str] | None = None) -> int`.
- CLI: `zeitgeist-doc-index build --repo NAME=PATH [--repo ...] [--include GLOB ...] [--index-dir PATH]`.
- CLI: `zeitgeist-doc-index search QUERY [--repo NAME ...] [--top-k N] [--index-dir PATH]`.
- Search prints score, repository, short commit, dirty marker, relative path, heading, and a bounded excerpt; it reports stale source repository state without rebuilding.

- [ ] **Step 1: Write failing CLI tests for argument parsing, build/search exit codes, formatted output, invalid `top-k`, and stale Git-state warnings.**
- [ ] **Step 2: Run `pytest -k cli -v` and verify expected failures.**
- [ ] **Step 3: Implement `argparse` commands, default `%LOCALAPPDATA%` index path resolution, stale-state comparison, output formatting, and console entry point.**
- [ ] **Step 4: Write `README.md` with exact Windows commands for building the three-repository index and querying it.**
- [ ] **Step 5: Run the full suite and commit with `git commit -m "Expose documentation index CLI"`.**
### Task 8: Real Ollama smoke test and three-repository index

**Files:**
- Modify only if a smoke-test defect is reproduced: `tooling/doc_index/doc_index.py`, `tooling/doc_index/test_doc_index.py`, or `tooling/doc_index/README.md`.

**Interfaces:**
- Uses the installed Ollama service and local `bge-m3` model through the production `OllamaEmbedder`.
- Produces the live index at `%LOCALAPPDATA%\Zeitgeist\doc-index` from explicit Zed, Glass, and Zeitgeist repository roots.

- [ ] **Step 1: Run the complete automated test suite.**
- [ ] **Step 2: Verify the installed Ollama model inventory contains `bge-m3` and perform one short embedding probe.**
- [ ] **Step 3: Build a small temporary real-model smoke index and verify a known semantic query retrieves the intended document.**
- [ ] **Step 4: Build the complete Zed/Glass/Zeitgeist Markdown index using explicit repository roots and validate it by reloading all persisted files.**
- [ ] **Step 5: Run comparative semantic queries for embedded browser, workspace modes, app runtime, service hub, terminal/agent layout, and Obsidian embedding requirements; record the top evidence used to resume the Glass relevance research.**
- [ ] **Step 6: Run `git status --short`, the complete test suite again, and inspect the final diff before claiming completion.**
- [ ] **Step 7: Commit any final smoke-test fixes separately; do not commit `%LOCALAPPDATA%` index artifacts into Git.**

## Verification Notes

Official Ollama API documentation verified on 2026-08-13 specifies `POST /api/embed`, accepts either a string or array in `input`, and returns an embeddings matrix.

Ollama's embeddings guide states that the endpoint returns L2-normalized vectors and recommends cosine similarity with the same embedding model for both indexing and querying.

The implementation must still normalize defensively because the persistent-format contract requires normalized vectors independent of server behavior. `truncate` is sent as `false` so oversized chunks fail rather than being silently truncated; the chunker owns the 3,500-character limit.
