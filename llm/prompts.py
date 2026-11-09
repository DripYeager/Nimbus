"""
Prompt text: the assistant's system prompt, plus templates for summarizing and for answering
from retrieved excerpts when a model can't use tools. Owns prompt wording only — does not call
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
- When you open or launch something, call the tool — never claim you did it otherwise.
- If a tool says the user declined, accept it and don't retry the same action.
- Answer in short, plain Markdown. Name the files you used. If you couldn't find something, \
say so plainly and suggest what the user could try."""

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


def build_system_prompt(folders: list[str], now: datetime) -> str:
    """Fills the system prompt with the current time and the folders Nimbus may search."""
    folder_list = ", ".join(folders) if folders else "none yet"
    return SYSTEM_PROMPT.format(now=f"{now:%A %d %B %Y, %H:%M}", folders=folder_list)


def build_summarize_prompt(text: str) -> str:
    """Fills the summarization template with the document text to condense."""
    return SUMMARIZE_PROMPT.format(text=text)


def build_qa_prompt(question: str, chunks: list[SearchResult]) -> str:
    """Fills the QA template with retrieved chunks as context for the question."""
    context = "\n\n".join(f"[{chunk.file_name}] {chunk.chunk_text}" for chunk in chunks)
    return QA_PROMPT.format(context=context, question=question)
