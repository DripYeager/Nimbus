"""
Prompt templates for summarization, retrieval QA, and intent classification.
Owns prompt text only — does not call the LLM or know about retrieval mechanics.
"""

from __future__ import annotations

from models.schema import Intent, SearchResult

SUMMARIZE_PROMPT = """Summarize the following document in 5 concise bullet points. \
Focus on concrete facts, decisions, and numbers — skip generic filler.

Document:
{text}

Summary:"""

QA_PROMPT = """Answer the question using only the context below. If the context doesn't \
contain the answer, say so plainly instead of guessing. Cite the source file for each claim.

Context:
{context}

Question: {question}

Answer:"""

INTENT_CLASSIFY_PROMPT = """Classify the user's request into exactly one of these intents: \
{intents}. Reply with only the intent name, nothing else.

Request: {text}

Intent:"""


def build_summarize_prompt(text: str) -> str:
    """Fills the summarization template with the document text to condense."""
    return SUMMARIZE_PROMPT.format(text=text)


def build_qa_prompt(question: str, chunks: list[SearchResult]) -> str:
    """Fills the QA template with retrieved chunks as context for the question."""
    context = "\n\n".join(f"[{chunk.file_name}] {chunk.chunk_text}" for chunk in chunks)
    return QA_PROMPT.format(context=context, question=question)


def build_intent_classify_prompt(text: str) -> str:
    """Fills the intent-classification template with the request and the full intent list."""
    intents = ", ".join(intent.value for intent in Intent)
    return INTENT_CLASSIFY_PROMPT.format(intents=intents, text=text)
