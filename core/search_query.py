"""
Turns a user's question into a full-text (FTS5) query: keeps the meaningful words, drops
filler like "what" and "the", and quotes each word so codes such as "INV-2231" match exactly.
Pure text processing — does not run the query.
"""

from __future__ import annotations

import re

# Words common enough to match nearly every chunk. Leaving them in makes BM25 score the
# whole index for every question — slow on a big index and no help to ranking.
_STOP_WORDS_TEXT = """
    a about above after again all also am an and any are as at be because been before being
    below between both but by can could did do does doing down during each few for from
    further had has have having he her here hers him his how i if in into is it its itself
    just me more most my no nor not now of off on once only or other our out over own please
    same she should so some such than that the their them then there these they this those
    through to too under until up very was we were what when where which while who whom why
    will with would you your
    find show tell give get look say says said
"""
STOP_WORDS = frozenset(_STOP_WORDS_TEXT.split())
TERM_PATTERN = re.compile(r"[^\s\"]+")
# Trailing punctuation from the sentence ("termination?") isn't part of the word.
EDGE_PUNCTUATION = ".,;:!?()[]{}'"
MAX_TERMS = 12


def build_fts_query(text: str) -> str | None:
    """An OR-query of the quoted meaningful words in text, or None if none are left."""
    terms: list[str] = []
    for raw in TERM_PATTERN.findall(text):
        term = raw.strip(EDGE_PUNCTUATION)
        if term and term.lower() not in STOP_WORDS and term.lower() not in (t.lower() for t in terms):
            terms.append(term)
    if not terms:
        return None
    return " OR ".join(f'"{term}"' for term in terms[:MAX_TERMS])
