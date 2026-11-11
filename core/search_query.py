"""
Turns a user's question into a full-text (FTS5) query: keeps the meaningful words, drops
filler like "what" and "the", and quotes each word so codes such as "INV-2231" match exactly.
Also decides how much keyword matching should count for a question. Pure text processing, does
not run the query.
"""

from __future__ import annotations

import re

# Words common enough to match nearly every chunk. Leaving them in makes BM25 score the
# whole index for every question, slow on a big index and no help to ranking.
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


# Keyword search earns its place for exact things: codes (anything with a digit, like "INV-2231"
# or "E119"), acronyms ("VPN"), quoted phrases and names. For a plain question ("how much did we
# pay for the desks") its OR-of-words ranking is noise: "pay" matches every invoice. On the
# 100-document benchmark, fusing it at full weight for such questions cut top-1 accuracy on
# paraphrases from 0.72 to 0.40.
_DIGIT_OR_QUOTE = re.compile(r"\d|\"")
_ACRONYM = re.compile(r"\b[A-Z]{2,}\b")
_CAPITALIZED = re.compile(r"[A-Z][a-z]+")
_SENTENCE_BREAK = re.compile(r"[.?!\n]+")
_WORD_EDGES = "\"'(),;:"
# Capitalized for reasons other than being a name, so they say nothing about exactness.
NOT_NAMES = frozenset(
    [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "nimbus",
        "hey",
        "hi",
        "hello",
        "please",
        "thanks",
    ]
)
NOT_ACRONYMS = frozenset({"OK", "AM", "PM", "I'M", "TV"})
KEYWORD_WEIGHT_EXACT = 1.0
KEYWORD_WEIGHT_NATURAL = 0.0


def keyword_weight(text: str) -> float:
    """How much keyword ranking should count when fused with meaning-based ranking."""
    has_acronym = any(match not in NOT_ACRONYMS for match in _ACRONYM.findall(text))
    if _DIGIT_OR_QUOTE.search(text) or has_acronym or _has_name(text):
        return KEYWORD_WEIGHT_EXACT
    return KEYWORD_WEIGHT_NATURAL


def _has_name(text: str) -> bool:
    """A capitalized word that isn't the first of its sentence (or a weekday, month or greeting):
    a person, place or product. Sentences break at . ? ! or a new line, however much space follows."""
    for sentence in _SENTENCE_BREAK.split(text):
        words = [word.strip(_WORD_EDGES) for word in sentence.split()]
        for word in words[1:]:
            if _CAPITALIZED.fullmatch(word) and word.lower() not in NOT_NAMES:
                return True
    return False
