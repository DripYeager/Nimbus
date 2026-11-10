"""
Prompt text: the assistant's system prompt, plus templates for summarizing and for answering
from retrieved excerpts when a model can't use tools. Owns prompt wording only; it does not call
the LLM or know about retrieval mechanics.
"""

from __future__ import annotations

from datetime import datetime

from models.schema import SearchResult

SYSTEM_PROMPT = """You are Nimbus, a private assistant that lives on the user's Windows PC. \
You can search and read the files the user has shared with you, open apps, files, websites and \
Windows settings, check the machine's status, and keep notes.

Current local time: {now}
Folders you can see: {folders}

How to work:
- Use tools to find facts. Never invent file names, paths, contents, or results.
- To answer about the user's documents, search first (search_files for topics, \
find_files_by_name for names), then read_file the best match if you need detail.
- When you open or launch something, call the tool. Never claim you did it otherwise.
- If a tool says the user declined, accept it and don't retry the same action.
- Answer in short, plain Markdown. Name the files you used. If you couldn't find something, \
say so plainly and suggest what the user could try.
- A message can end with an <attachment> block: a file, copied text or a screenshot the user \
handed you. Answer about it directly; don't search for it or try to open it.
- When a search result shows a page, cite it with the file, like (Report.pdf, p. 12).
- Write in plain sentences. Never use em dashes or en dashes; use a comma, colon or full stop."""

SUMMARIZE_PROMPT = """Summarize the following document in 5 concise bullet points. \
Focus on concrete facts, decisions, and numbers, and skip generic filler. \
Never use em dashes or en dashes.

Document:
{text}

Summary:"""

QA_PROMPT = """Answer the question using only the context below. If the context doesn't \
contain the answer, say so plainly instead of guessing. Cite the source file for each claim. \
Never use em dashes or en dashes.

Context:
{context}

Question: {question}

Answer:"""


def build_system_prompt(folders: list[str], now: datetime) -> str:
    """Fills the system prompt with the current time and the folders Nimbus may search."""
    folder_list = ", ".join(folders) if folders else "none yet"
    return SYSTEM_PROMPT.format(now=f"{now:%A %d %B %Y, %H:%M}", folders=folder_list)


def build_summarize_prompt(text: str) -> str:
    """Fills the summarization template with the document text to condense."""
    return SUMMARIZE_PROMPT.format(text=text)


def build_qa_prompt(question: str, chunks: list[SearchResult]) -> str:
    """Fills the QA template with retrieved chunks as context for the question."""
    context = "\n\n".join(f"[{_cite(chunk)}] {chunk.chunk_text}" for chunk in chunks)
    return QA_PROMPT.format(context=context, question=question)


def _cite(chunk: SearchResult) -> str:
    """How an excerpt is labelled in the prompt: the file name, plus its page when known."""
    return f"{chunk.file_name}, p. {chunk.page}" if chunk.page is not None else chunk.file_name
