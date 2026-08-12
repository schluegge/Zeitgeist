# Documentation Vector Index Design

Date: 2026-08-12
Status: approved design, pre-implementation
Base: `integration/zed-first-2026-08-12` at `ba0e2a94295c99f48f00cdaa2858a29adae6f09d`

## Goal

Build a persistent local semantic index for the documentation of Zed, Glass, and Zeitgeist so comparative research can retrieve conceptually relevant documentation without relying on repeated keyword searches.

## Scope

The first version indexes Markdown documentation only. Repository roots are supplied explicitly at build time rather than hard-coded, and each indexed source is tagged with a caller-provided repository name.

The default corpus for each repository is `docs/**/*.md`. Additional Markdown paths may be supplied explicitly when needed. Source code is deliberately excluded from the vector index; exact code verification remains a separate step after semantic documentation retrieval.

## Architecture

The indexer chunks Markdown by heading and paragraph boundaries, preserving heading context and fenced code blocks. Chunks are capped at 3,500 characters with up to 300 characters of overlap when a section must be split.

Embeddings are produced locally by Ollama using the already-installed `bge-m3` model. No hosted embedding API is required. Embeddings are normalized and stored as `float32` vectors.
Identical chunk content is deduplicated by SHA-256 before embedding. A unique chunk keeps all source locations that contain that content, so cross-repository duplication remains visible without storing duplicate vectors.

Search embeds the query with the same model, normalizes it, and ranks all stored vectors by cosine similarity using a NumPy matrix-vector dot product. At the current corpus size, an approximate-nearest-neighbor service such as FAISS or Qdrant adds infrastructure without a retrieval benefit.

## Persistent Format

The index lives outside the repositories under `%LOCALAPPDATA%\Zeitgeist\doc-index` and contains:

- `manifest.json`: schema version, embedding model, vector dimension, build timestamp, corpus configuration, and source repository Git state.
- `chunks.jsonl`: one record per unique chunk with content hash, text, heading context, and all source locations.
- `vectors.npy`: row-aligned normalized `float32` embeddings.

Each source location records `repo`, `commit`, `dirty`, `relative_path`, and `chunk_index`. This makes every retrieval result traceable to the exact repository state that was indexed.

A build writes to a temporary sibling directory and only replaces the active index after all files validate successfully. A failed or interrupted build must leave the previous index usable.

## Command Interface

The tool exposes two operations:

```text
build  --repo NAME=PATH [--repo NAME=PATH ...] [--include GLOB ...]
search QUERY [--repo NAME ...] [--top-k N]
```

`build` performs a complete deterministic rebuild. `search` loads the persisted index, embeds the query, applies optional repository filters, and prints ranked results with score, repository, commit, path, heading, and excerpt.
## Failure Handling

The build fails clearly if a repository path is invalid, Git state cannot be read, Ollama is unavailable, `bge-m3` is missing, an embedding response has an unexpected dimension, or persisted files fail alignment checks.

Search refuses to use an index whose manifest schema, model, vector dimension, chunk count, or vector row count is inconsistent. It reports stale repository metadata but does not silently rebuild.

## Testing

Unit tests cover Markdown chunk boundaries, fenced-code preservation, overlap behavior, SHA-256 deduplication, source aggregation, repository filtering, and cosine ranking with fixed vectors.

Integration tests use a fake local embedding endpoint so correctness does not depend on model output. A separate local smoke test builds a small real index through Ollama `bge-m3`, reloads it from disk, and retrieves a known semantic match.

## Non-Goals

- No source-code vector indexing in v1.
- No hosted embedding provider.
- No Qdrant, FAISS, or other vector database.
- No automatic background watcher or rebuild daemon.
- No mutation of Zed, Glass, or Zeitgeist documentation during indexing.
- No claim that semantic retrieval replaces exact code inspection for implementation decisions.

## Acceptance Criteria

A clean build over the three documentation corpora produces a reloadable persistent index under `%LOCALAPPDATA%\Zeitgeist\doc-index`. Repeating the build against identical repository states produces the same chunk hashes and source mappings. A semantic query can return ranked results across all three repositories or a selected subset, and every result identifies the repository, commit, path, and heading from which it came.