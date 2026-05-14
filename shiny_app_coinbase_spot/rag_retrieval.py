# rag_retrieval.py
# Lightweight RAG over data/knowledge_base.md (keyword overlap scoring)
# Coinbase Spot Reporter — App V2 / V3
# Prof. Tim Fraser pattern

# Topic: retrieve playbook chunks for AI agents without extra vector DB deps.
# Students: tune chunking or scoring if you adopt embeddings later.

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent
_DEFAULT_KB = _ROOT / "data" / "knowledge_base.md"


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


def load_playbook_chunks(path: Path | None = None) -> list[tuple[str, str]]:
    """Return (heading, body) sections split on ## headings."""
    path = path or _DEFAULT_KB
    raw = path.read_text(encoding="utf-8")
    chunks: list[tuple[str, str]] = []
    parts = re.split(r"\n##\s+", raw.strip())
    for part in parts:
        part = part.strip()
        if not part:
            continue
        lines = part.split("\n", 1)
        title = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        chunks.append((title, body))
    return chunks


def search_playbook(query: str, *, top_k: int = 2, path: Path | None = None) -> str:
    """
    Rank sections by token overlap with the query; return markdown text for the model.
    """
    q_tokens = _tokenize(query or "")
    if not q_tokens:
        return "No playbook snippets retrieved (empty query)."

    chunks = load_playbook_chunks(path)
    scored: list[tuple[float, str, str]] = []
    for title, body in chunks:
        blob = f"{title}\n{body}"
        c_tokens = _tokenize(blob)
        hit = len(q_tokens & c_tokens)
        score = hit / max(1, len(q_tokens))
        scored.append((score, title, body))

    scored.sort(key=lambda x: (-x[0], x[1]))
    picked = [item for item in scored if item[0] > 0][:top_k]
    if not picked:
        picked = scored[:top_k]

    lines: list[str] = ["### Retrieved playbook excerpts (RAG)\n"]
    for score, title, body in picked:
        lines.append(f"#### {title}\n_relevance_score={score:.3f}_\n{body}\n")
    return "\n".join(lines)


def rag_tool_result(query: str) -> dict[str, Any]:
    """Structured payload for logging / QC (optional)."""
    text = search_playbook(query)
    return {"query": query, "excerpt_chars": len(text), "preview": text[:400]}
