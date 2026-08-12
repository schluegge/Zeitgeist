from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Sequence
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from urllib import error as urllib_error
from urllib import request as urllib_request

import numpy as np


@dataclass(frozen=True)
class SourceRepo:
    name: str
    path: Path
    commit: str
    dirty: bool


@dataclass(frozen=True)
class ChunkLocation:
    repo: str
    commit: str
    dirty: bool
    relative_path: str
    chunk_index: int
    heading: str


@dataclass
class ChunkRecord:
    content_hash: str
    text: str
    locations: list[ChunkLocation] = field(default_factory=list)


@dataclass(frozen=True)
class IndexManifest:
    schema_version: int
    model: str
    vector_dimension: int
    chunk_count: int
    built_at: str
    repositories: list[dict]
    include_globs: list[str]


@dataclass
class SearchResult:
    score: float
    chunk: ChunkRecord
    matched_locations: list[ChunkLocation]


def discover_markdown(repo_path: Path, include_globs: Sequence[str]) -> list[Path]:
    discovered: dict[str, Path] = {}
    for pattern in include_globs:
        for path in repo_path.glob(pattern):
            if path.is_file() and path.suffix.lower() == ".md":
                relative = path.relative_to(repo_path).as_posix()
                discovered[relative] = path
    return [discovered[key] for key in sorted(discovered)]


def _heading_path(headings: list[str | None]) -> str:
    return " > ".join(heading for heading in headings if heading)


def _split_blocks(lines: list[str]) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    fence: str | None = None

    def flush() -> None:
        text = "\n".join(current).strip()
        if text:
            blocks.append(text)
        current.clear()

    for line in lines:
        stripped = line.lstrip()
        marker = None
        if stripped.startswith("```"):
            marker = "```"
        elif stripped.startswith("~~~"):
            marker = "~~~"

        if marker is not None:
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            current.append(line)
            continue

        if not line.strip() and fence is None:
            flush()
        else:
            current.append(line)

    flush()
    return blocks


def _split_plain_text(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            split_at = text.rfind(" ", start + max_chars // 2, end)
            if split_at > start:
                end = split_at
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= len(text):
            break
        next_start = max(end - overlap_chars, start + 1)
        start = next_start
    return pieces


def _split_fenced_block(block: str, max_chars: int) -> list[str]:
    if len(block) <= max_chars:
        return [block]
    lines = block.splitlines()
    if len(lines) < 3:
        raise ValueError("oversized fenced block has no splittable body")
    opener = lines[0]
    marker = "```" if opener.lstrip().startswith("```") else "~~~"
    closer = lines[-1]
    if not closer.lstrip().startswith(marker):
        raise ValueError("oversized fenced block is not balanced")
    available = max_chars - len(opener) - len(closer) - 2
    if available <= 0:
        raise ValueError("max_chars is too small to preserve fenced Markdown delimiters")

    body_pieces: list[str] = []
    current_lines: list[str] = []
    for line in lines[1:-1]:
        candidate = "\n".join([*current_lines, line])
        if current_lines and len(candidate) > available:
            body_pieces.append("\n".join(current_lines))
            current_lines = []
        if len(line) > available:
            body_pieces.extend(line[start : start + available] for start in range(0, len(line), available))
        else:
            current_lines.append(line)
    if current_lines:
        body_pieces.append("\n".join(current_lines))
    return [f"{opener}\n{body}\n{closer}" for body in body_pieces]


def _pack_blocks(blocks: list[str], max_chars: int, overlap_chars: int) -> list[str]:
    packed: list[str] = []
    current = ""
    for block in blocks:
        is_fenced = block.startswith(("```", "~~~"))
        if is_fenced and len(block) > max_chars:
            if current:
                packed.append(current)
                current = ""
            packed.extend(_split_fenced_block(block, max_chars))
            continue
        pieces = [block] if is_fenced else _split_plain_text(block, max_chars, overlap_chars)
        for piece in pieces:
            candidate = piece if not current else f"{current}\n\n{piece}"
            if len(candidate) <= max_chars:
                current = candidate
                continue
            if current:
                packed.append(current)
            overlap = packed[-1][-overlap_chars:].strip() if packed and overlap_chars else ""
            current = f"{overlap}\n\n{piece}".strip() if overlap else piece
            if len(current) > max_chars and overlap:
                allowance = max(max_chars - len(piece) - 2, 0)
                overlap = overlap[-allowance:] if allowance else ""
                current = f"{overlap}\n\n{piece}".strip() if overlap else piece
    if current:
        packed.append(current)
    return packed


def chunk_markdown(
    text: str,
    max_chars: int = 3500,
    overlap_chars: int = 300,
) -> list[tuple[str, str]]:
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be non-negative and smaller than max_chars")

    headings: list[str | None] = []
    section_lines: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    fence: str | None = None

    def flush_section() -> None:
        if any(line.strip() for line in section_lines):
            sections.append((_heading_path(headings), list(section_lines)))
        section_lines.clear()

    for line in text.splitlines():
        stripped = line.lstrip()
        marker = None
        if stripped.startswith("```"):
            marker = "```"
        elif stripped.startswith("~~~"):
            marker = "~~~"

        if marker is not None:
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            section_lines.append(line)
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line) if fence is None else None
        if heading_match:
            flush_section()
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            if len(headings) < level:
                headings.extend([None] * (level - len(headings)))
            headings[level - 1] = title
            del headings[level:]
            continue

        section_lines.append(line)

    flush_section()

    chunks: list[tuple[str, str]] = []
    for heading, lines in sections:
        blocks = _split_blocks(lines)
        for packed in _pack_blocks(blocks, max_chars, overlap_chars):
            chunks.append((heading, packed))
    return chunks


def _git_output(repo_path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def read_git_state(name: str, repo_path: Path) -> SourceRepo:
    commit = _git_output(repo_path, "rev-parse", "HEAD")
    dirty = bool(_git_output(repo_path, "status", "--porcelain=v1"))
    return SourceRepo(name=name, path=repo_path, commit=commit, dirty=dirty)


def collect_chunks(
    repositories: Sequence[SourceRepo],
    include_globs: Sequence[str],
) -> list[ChunkRecord]:
    by_hash: dict[str, ChunkRecord] = {}
    for repository in sorted(repositories, key=lambda item: item.name):
        for path in discover_markdown(repository.path, include_globs):
            relative_path = path.relative_to(repository.path).as_posix()
            markdown = path.read_text(encoding="utf-8-sig")
            for chunk_index, (heading, chunk_text) in enumerate(chunk_markdown(markdown)):
                content_hash = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
                location = ChunkLocation(
                    repo=repository.name,
                    commit=repository.commit,
                    dirty=repository.dirty,
                    relative_path=relative_path,
                    chunk_index=chunk_index,
                    heading=heading,
                )
                record = by_hash.get(content_hash)
                if record is None:
                    by_hash[content_hash] = ChunkRecord(
                        content_hash=content_hash,
                        text=chunk_text,
                        locations=[location],
                    )
                else:
                    if record.text != chunk_text:
                        raise ValueError(f"SHA-256 collision for chunk {content_hash}")
                    record.locations.append(location)
    return list(by_hash.values())


class OllamaEmbedder:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "bge-m3",
        timeout_seconds: float = 60.0,
        batch_size: int = 128,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.batch_size = batch_size

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            raise ValueError("at least one text is required for embedding")
        if len(texts) > self.batch_size:
            batches = [
                self.embed(texts[start : start + self.batch_size])
                for start in range(0, len(texts), self.batch_size)
            ]
            dimensions = {batch.shape[1] for batch in batches}
            if len(dimensions) != 1:
                raise RuntimeError("Ollama embedding dimension mismatch across batches")
            return np.concatenate(batches, axis=0).astype(np.float32, copy=False)
        payload = json.dumps(
            {"model": self.model, "input": list(texts), "truncate": False}
        ).encode("utf-8")
        request = urllib_request.Request(
            f"{self.base_url}/api/embed",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw_body = response.read()
        except (urllib_error.HTTPError, urllib_error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"Ollama embedding request failed: {exc}") from exc

        try:
            decoded = json.loads(raw_body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError("Ollama embedding response was not valid JSON") from exc

        embeddings = decoded.get("embeddings") if isinstance(decoded, dict) else None
        if not isinstance(embeddings, list):
            raise RuntimeError("Ollama embedding response did not contain an embeddings array")
        if len(embeddings) != len(texts):
            raise RuntimeError(
                f"Ollama returned {len(embeddings)} embeddings for {len(texts)} inputs"
            )
        if not embeddings or not all(isinstance(vector, list) for vector in embeddings):
            raise RuntimeError("Ollama embedding response contained invalid vectors")

        dimensions = {len(vector) for vector in embeddings}
        if len(dimensions) != 1:
            raise RuntimeError("Ollama embedding dimension mismatch within response")
        dimension = next(iter(dimensions))
        if dimension <= 0:
            raise RuntimeError("Ollama returned zero-width embeddings")

        try:
            vectors = np.asarray(embeddings, dtype=np.float32)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("Ollama embedding response contained non-numeric values") from exc
        if vectors.ndim != 2 or vectors.shape != (len(texts), dimension):
            raise RuntimeError("Ollama embedding response had an unexpected matrix shape")
        if not np.isfinite(vectors).all():
            raise RuntimeError("Ollama embedding response contained non-finite values")

        norms = np.linalg.norm(vectors, axis=1)
        if np.any(norms == 0):
            raise RuntimeError("Ollama embedding response contained a zero vector")
        normalized = vectors / norms[:, np.newaxis]
        return normalized.astype(np.float32, copy=False)


def _validate_index_components(
    manifest: IndexManifest,
    chunks: Sequence[ChunkRecord],
    vectors: np.ndarray,
    error_type=ValueError,
) -> None:
    if vectors.ndim != 2:
        raise error_type("vectors must be a two-dimensional matrix")
    if vectors.shape[0] != len(chunks):
        raise error_type("vector row count does not match chunk count")
    if manifest.chunk_count != len(chunks):
        raise error_type("manifest chunk count does not match chunks")
    if vectors.shape[1] != manifest.vector_dimension:
        raise error_type("manifest vector dimension does not match vectors")
    if vectors.dtype != np.float32:
        raise error_type("vectors must use float32 dtype")
    if not np.isfinite(vectors).all():
        raise error_type("vectors contain non-finite values")
    if len(chunks):
        norms = np.linalg.norm(vectors, axis=1)
        if not np.allclose(norms, 1.0, atol=1e-5):
            raise error_type("vectors must be L2-normalized")


def _record_to_dict(record: ChunkRecord) -> dict:
    return {
        "content_hash": record.content_hash,
        "text": record.text,
        "locations": [asdict(location) for location in record.locations],
    }


def _record_from_dict(raw: dict) -> ChunkRecord:
    try:
        locations = [ChunkLocation(**location) for location in raw["locations"]]
        return ChunkRecord(
            content_hash=str(raw["content_hash"]),
            text=str(raw["text"]),
            locations=locations,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("chunks metadata is invalid") from exc


def write_index(
    index_dir: Path,
    manifest: IndexManifest,
    chunks: Sequence[ChunkRecord],
    vectors: np.ndarray,
) -> None:
    _validate_index_components(manifest, chunks, vectors)
    index_dir = Path(index_dir)
    index_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{index_dir.name}.staging-", dir=index_dir.parent))
    backup = index_dir.parent / f".{index_dir.name}.backup-{uuid.uuid4().hex}"
    try:
        (staging / "manifest.json").write_text(
            json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with (staging / "chunks.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for record in chunks:
                handle.write(json.dumps(_record_to_dict(record), sort_keys=True, ensure_ascii=False))
                handle.write("\n")
        np.save(staging / "vectors.npy", vectors, allow_pickle=False)

        load_index(staging, expected_model=manifest.model)

        had_previous = index_dir.exists()
        if had_previous:
            os.replace(index_dir, backup)
        try:
            os.replace(staging, index_dir)
        except Exception:
            if had_previous and backup.exists() and not index_dir.exists():
                os.replace(backup, index_dir)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if backup.exists() and index_dir.exists():
            shutil.rmtree(backup, ignore_errors=True)


def load_index(
    index_dir: Path,
    expected_model: str = "bge-m3",
) -> tuple[IndexManifest, list[ChunkRecord], np.ndarray]:
    index_dir = Path(index_dir)
    try:
        raw_manifest = json.loads((index_dir / "manifest.json").read_text(encoding="utf-8"))
        manifest = IndexManifest(**raw_manifest)
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError("index manifest is missing or invalid") from exc

    if manifest.schema_version != 1:
        raise RuntimeError(f"unsupported index schema version: {manifest.schema_version}")
    if manifest.model != expected_model:
        raise RuntimeError(
            f"index embedding model {manifest.model!r} does not match expected model {expected_model!r}"
        )

    chunks: list[ChunkRecord] = []
    try:
        with (index_dir / "chunks.jsonl").open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                raw_record = json.loads(line)
                chunks.append(_record_from_dict(raw_record))
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        raise RuntimeError("index chunks metadata is missing or invalid") from exc

    for record in chunks:
        expected_hash = hashlib.sha256(record.text.encode("utf-8")).hexdigest()
        if record.content_hash != expected_hash:
            raise RuntimeError("index chunks metadata contains a content hash mismatch")

    try:
        vectors = np.load(index_dir / "vectors.npy", allow_pickle=False)
    except (OSError, ValueError) as exc:
        raise RuntimeError("index vectors are missing or invalid") from exc

    _validate_index_components(manifest, chunks, vectors, error_type=RuntimeError)
    return manifest, chunks, vectors


DEFAULT_INCLUDE_GLOB = "docs/**/*.md"


def _parse_repo_specs(repo_specs: Sequence[str]) -> list[SourceRepo]:
    if not repo_specs:
        raise ValueError("at least one --repo NAME=PATH value is required")
    repositories: list[SourceRepo] = []
    names: set[str] = set()
    for spec in repo_specs:
        if "=" not in spec:
            raise ValueError(f"repository must use NAME=PATH syntax: {spec!r}")
        name, raw_path = spec.split("=", 1)
        name = name.strip()
        raw_path = raw_path.strip()
        if not name or not raw_path:
            raise ValueError(f"repository must use NAME=PATH syntax: {spec!r}")
        if name in names:
            raise ValueError(f"duplicate repository name: {name}")
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            raise ValueError(f"repository path does not exist: {path}")
        if not path.is_dir():
            raise ValueError(f"repository path is not a directory: {path}")
        try:
            repository = read_git_state(name, path)
        except (subprocess.CalledProcessError, OSError) as exc:
            raise ValueError(f"repository path is not a readable Git checkout: {path}") from exc
        names.add(name)
        repositories.append(repository)
    return sorted(repositories, key=lambda item: item.name)


def _effective_include_globs(include_globs: Sequence[str]) -> list[str]:
    result = [DEFAULT_INCLUDE_GLOB]
    for pattern in include_globs:
        if pattern and pattern not in result:
            result.append(pattern)
    return result


def build_index(
    repo_specs: Sequence[str],
    include_globs: Sequence[str],
    index_dir: Path,
    embedder: OllamaEmbedder,
) -> IndexManifest:
    repositories = _parse_repo_specs(repo_specs)
    effective_globs = _effective_include_globs(include_globs)
    chunks = collect_chunks(repositories, effective_globs)
    if not chunks:
        raise ValueError("documentation corpus produced no Markdown chunks")
    vectors = embedder.embed([chunk.text for chunk in chunks])
    if vectors.ndim != 2 or vectors.shape[0] != len(chunks):
        raise RuntimeError("embedding matrix shape does not match collected chunks")
    model = getattr(embedder, "model", None)
    if not isinstance(model, str) or not model:
        raise RuntimeError("embedding provider did not expose a model name")

    manifest = IndexManifest(
        schema_version=1,
        model=model,
        vector_dimension=int(vectors.shape[1]),
        chunk_count=len(chunks),
        built_at=datetime.now(timezone.utc).isoformat(),
        repositories=[
            {
                "name": repository.name,
                "path": str(repository.path),
                "commit": repository.commit,
                "dirty": repository.dirty,
            }
            for repository in repositories
        ],
        include_globs=effective_globs,
    )
    write_index(Path(index_dir), manifest, chunks, vectors)
    return manifest


def search_index(
    query: str,
    index_dir: Path,
    embedder: OllamaEmbedder,
    repo_filters: Sequence[str],
    top_k: int,
) -> list[SearchResult]:
    if not query.strip():
        raise ValueError("query must not be empty")
    if top_k <= 0:
        raise ValueError("top-k must be positive")
    model = getattr(embedder, "model", None)
    if not isinstance(model, str) or not model:
        raise RuntimeError("embedding provider did not expose a model name")

    manifest, chunks, vectors = load_index(Path(index_dir), expected_model=model)
    available_repositories = {str(repo["name"]) for repo in manifest.repositories}
    requested_repositories = list(dict.fromkeys(repo_filters))
    unknown = sorted(set(requested_repositories) - available_repositories)
    if unknown:
        raise ValueError(f"unknown repository filter: {', '.join(unknown)}")
    query_matrix = embedder.embed([query])
    if query_matrix.ndim != 2 or query_matrix.shape != (1, manifest.vector_dimension):
        raise RuntimeError("query embedding dimension does not match persisted index")
    query_vector = np.asarray(query_matrix[0], dtype=np.float32)
    if not np.isfinite(query_vector).all():
        raise RuntimeError("query embedding contains non-finite values")
    norm = float(np.linalg.norm(query_vector))
    if norm == 0.0:
        raise RuntimeError("query embedding is a zero vector")
    query_vector = query_vector / norm

    scores = vectors @ query_vector
    candidates: list[tuple[int, list[ChunkLocation]]] = []
    requested_set = set(requested_repositories)
    for row_index, chunk in enumerate(chunks):
        if requested_set:
            matched = [location for location in chunk.locations if location.repo in requested_set]
        else:
            matched = list(chunk.locations)
        if matched:
            candidates.append((row_index, matched))

    candidates.sort(key=lambda item: (-float(scores[item[0]]), item[0]))
    return [
        SearchResult(float(scores[row_index]), chunks[row_index], matched_locations)
        for row_index, matched_locations in candidates[:top_k]
    ]


def _configure_console_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def default_index_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("LOCALAPPDATA is not set; pass --index-dir explicitly")
    return Path(local_app_data) / "Zeitgeist" / "doc-index"


def _stale_repository_messages(manifest: IndexManifest) -> list[str]:
    messages: list[str] = []
    for indexed in manifest.repositories:
        name = str(indexed.get("name", ""))
        path = Path(str(indexed.get("path", "")))
        try:
            current = read_git_state(name, path)
        except (subprocess.CalledProcessError, OSError):
            messages.append(f"index source {name} is stale: repository is unavailable at {path}")
            continue
        indexed_commit = str(indexed.get("commit", ""))
        indexed_dirty = bool(indexed.get("dirty", False))
        if current.commit != indexed_commit or current.dirty != indexed_dirty:
            messages.append(
                f"index source {name} is stale: indexed {indexed_commit[:10]} "
                f"dirty={indexed_dirty}; current {current.commit[:10]} dirty={current.dirty}"
            )
    return messages


def _excerpt(text: str, limit: int = 240) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + chr(0x2026)


def _print_search_results(results: Sequence[SearchResult]) -> None:
    for rank, result in enumerate(results, start=1):
        print(f"{rank}. {result.score:.4f}")
        for location in result.matched_locations:
            dirty_marker = "*" if location.dirty else ""
            heading = f"  # {location.heading}" if location.heading else ""
            print(
                f"   {location.repo}@{location.commit[:10]}{dirty_marker}  "
                f"{location.relative_path}{heading}"
            )
        print(f"   {_excerpt(result.chunk.text)}")


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zeitgeist-doc-index")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build", help="build a complete documentation index")
    build_parser.add_argument("--repo", action="append", required=True, metavar="NAME=PATH")
    build_parser.add_argument("--include", action="append", default=[], metavar="GLOB")
    build_parser.add_argument("--index-dir", type=Path)

    search_parser = subparsers.add_parser("search", help="search the persisted documentation index")
    search_parser.add_argument("query")
    search_parser.add_argument("--repo", action="append", default=[], metavar="NAME")
    search_parser.add_argument("--top-k", type=int, default=10)
    search_parser.add_argument("--index-dir", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    _configure_console_streams()
    parser = _argument_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    try:
        index_dir = args.index_dir if args.index_dir is not None else default_index_dir()
        embedder = OllamaEmbedder()
        if args.command == "build":
            manifest = build_index(args.repo, args.include, index_dir, embedder)
            print(f"Built {manifest.chunk_count} unique chunks at {index_dir}")
            return 0

        if args.top_k <= 0:
            raise ValueError("top-k must be positive")
        manifest, _chunks, _vectors = load_index(index_dir, expected_model=embedder.model)
        for message in _stale_repository_messages(manifest):
            print(f"WARNING: {message}", file=sys.stderr)
        results = search_index(args.query, index_dir, embedder, args.repo, args.top_k)
        if results:
            _print_search_results(results)
        else:
            print("No matching documentation chunks.")
        return 0
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
