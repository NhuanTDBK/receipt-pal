"""FAQ tool — answers common product/feature questions from a static corpus.

Backed by ``docs/faq.md`` (shared between POC and backend).  Matching is a
simple keyword search over the corpus so answers remain deterministic and
require no DB or LLM call.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated

from agents import RunContextWrapper, function_tool

from app.services.agent_context import TelegramAgentContext

_FAQ_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / "docs" / "faq.md"


def _load_corpus() -> str:
    try:
        text = _FAQ_PATH.read_text(encoding="utf-8")
        return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    except OSError:
        return ""


def _extract_entries(corpus: str) -> list[dict[str, str]]:
    """Parse ``## Q: … / A: …`` sections from the markdown corpus."""
    entries: list[dict[str, str]] = []
    pattern = re.compile(
        r"##\s+Q:\s*(?P<question>.+?)\n+A:\s*(?P<answer>.+?)(?=\n##\s+Q:|\Z)",
        re.DOTALL,
    )
    for match in pattern.finditer(corpus):
        entries.append({
            "question": match.group("question").strip(),
            "answer": match.group("answer").strip(),
        })
    return entries


def _score(entry: dict[str, str], terms: list[str]) -> int:
    """Return how many query terms appear in the question + answer."""
    haystack = (entry["question"] + " " + entry["answer"]).lower()
    return sum(1 for t in terms if t in haystack)


@function_tool
async def answer_faq(
    ctx: RunContextWrapper[TelegramAgentContext],
    question: Annotated[str, "The user's product or feature question"],
) -> str:
    """Look up a question in the Receipt-Pal FAQ corpus.

    Use this tool when the user asks about how Receipt-Pal works, what
    categories are supported, how data is stored, or any general product
    question that does not require querying their receipt history.
    Returns the best-matching FAQ entry or a 'not found' message.
    """
    corpus = _load_corpus()
    if not corpus:
        return "FAQ corpus not available."

    entries = _extract_entries(corpus)
    if not entries:
        return "FAQ corpus is empty or could not be parsed."

    terms = [t.lower() for t in re.split(r"\W+", question) if len(t) > 2]
    if not terms:
        return "Please provide a more specific question."

    scored = [(entry, _score(entry, terms)) for entry in entries]
    scored.sort(key=lambda x: x[1], reverse=True)

    best_entry, best_score = scored[0]
    if best_score == 0:
        return (
            "No FAQ entry matched your question. "
            "Try rephrasing or ask me to query your receipt data directly."
        )

    return f"**Q: {best_entry['question']}**\n\n{best_entry['answer']}"