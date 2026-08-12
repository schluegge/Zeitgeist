from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Sequence
import hashlib
import json
import re
import subprocess
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


def _pack_blocks(blocks: list[str], max_chars: int, overlap_chars: int) -> list[str]:
    packed: list[str] = []
    current = ""
    for block in blocks:
        if block.startswith(("```", "~~~")):
            pieces = [block]
        else:
            pieces = _split_plain_text(block, max_chars, overlap_chars)
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
            markdown = path.read_text(encoding="utf-8")
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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            raise ValueError("at least one text is required for embedding")
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
