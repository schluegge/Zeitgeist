# Zeitgeist Documentation Vector Index

This tool builds and searches a local semantic index over Markdown documentation from explicit Git repositories. It is intended for comparative Zed, Glass, and Zeitgeist research.

## Requirements

- Python 3.13 or newer through `uv`.
- A running local Ollama installation.
- The Ollama model `bge-m3` installed locally.
- Git available on `PATH`.

The default index location is `%LOCALAPPDATA%\Zeitgeist\doc-index`.

## Build the index on Windows

From the Zeitgeist repository root:

```powershell
uv run --project tooling/doc_index zeitgeist-doc-index build `
  --repo zed=C:\path\to\zed `
  --repo glass=C:\path\to\Glass `
  --repo zeitgeist=C:\path\to\Zeitgeist `
  --include "crates/**/docs/**/*.md"
```

Each repository contributes `docs/**/*.md` by default. The comparative research build above also includes crate-local design documentation, which is where Glass keeps its Workspace Modes design. Add other Markdown corpora explicitly with `--include`:

```powershell
uv run --project tooling/doc_index zeitgeist-doc-index build `
  --repo zeitgeist=C:\path\to\Zeitgeist `
  --include "docs/architecture/**/*.md"
```

Use `--index-dir C:\some\directory` to override the default persistent location.

## Search

```powershell
uv run --project tooling/doc_index zeitgeist-doc-index search "embedded browser workspace mode" --top-k 8
```

Restrict results to one or more indexed repositories:

```powershell
uv run --project tooling/doc_index zeitgeist-doc-index search "terminal agent layout" `
  --repo zed `
  --repo glass `
  --top-k 10
```

Each result includes cosine score, repository, indexed commit, dirty marker, relative path, heading context, and an excerpt.

## Behavior and safety

- Builds are complete deterministic rebuilds of the selected Markdown corpus.
- Identical chunk text is embedded once and retains every source location.
- A new index is staged and validated before replacing the previous index.
- Search warns when a source repository's current Git commit/dirty state differs from the indexed state; it never rebuilds automatically.
- Source repositories are read-only inputs. The indexer does not rewrite documentation.
- Source code is not vector-indexed in v1. Use semantic documentation hits to guide subsequent exact code inspection.
