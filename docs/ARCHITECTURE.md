# Nimbus — Architecture

This document explains how Nimbus is put together and why. For setup and house style, see
[`CONTRIBUTING.md`](../CONTRIBUTING.md).

## 1. Constraints that shaped the design

| Constraint | Consequence |
|---|---|
| Must run on a locked-down work laptop with **no admin rights** | Plain user process; data in `%APPDATA%`; hotkey via `RegisterHotKey` (no keyboard hook); autostart via the Startup folder; no services or drivers |
| **Private by default** | Embeddings, search, chat history and notes are always local. A cloud model is an explicit, warned opt-in, and the UI shows a Local/Cloud badge |
| Must be **usable from the first second**, even on a 50k-file Documents folder | Two-tier index: an instant file-name catalog, and content indexing in the background with recent files first. Queries never wait for indexing |
| **Model choice belongs to the user** | One provider interface for Ollama, OpenAI, Anthropic and any OpenAI-compatible server, hot-swappable from Settings |
| Model calls cost money | Common commands ("open spotify", "find resume.pdf") are answered by a deterministic fast path with zero model calls; optional daily cap |

## 2. Process model

One user process, four kinds of thread:

```
┌───────────────────────── Qt main thread ──────────────────────────┐
│ ChatWindow (chat · history · settings pages) · Onboarding · Tray      │
└──────────────┬────────────────────────────────────────────────────┘
               │ HTTP + Server-Sent Events on 127.0.0.1 (never 0.0.0.0)
┌──────────────▼──────────── api-server thread (uvicorn) ───────────┐
│ FastAPI routes → ChatService → Agent → ToolRegistry → tools       │
│                         └→ ActiveProvider → Ollama/OpenAI/Anthropic│
└──────────────┬────────────────────────────────────────────────────┘
               │ in-process calls
┌──────────────▼──────── background threads ────────────────────────┐
│ index-scan (catalog sync) · index-worker (content) · watchdog     │
│ hotkey message loop · app-catalog build                            │
└───────────────────────────────────────────────────────────────────┘
```

The UI talks to the engine over a loopback HTTP boundary even though both live in one process.
That keeps the GUI thread thin, makes the engine fully testable with `curl` or a `TestClient`,
and means a UI bug can't corrupt indexing state.

`core/app_runtime.py` owns startup and shutdown; `core/service_container.py` is the engine's
composition root; `ui/desktop_shell.py` composes the UI.

## 3. Indexing

```
sources (Settings) ──► directory_scanner (os.scandir, prunes excluded dirs, stats only)
                          │
                          ▼
                     catalog_sync ── diff against catalog snapshot (size + mtime) ──┐
                          │                                                         │
              new/changed content files                                   vanished files
                          ▼                                                         ▼
                     IndexQueue (urgent watcher events first, then newest mtime)   purge
                          │
                          ▼
                     IndexWorker ──► Indexer: hash → parse → (OCR) → chunk → embed → search.db
                          │
                          ▼
                     FileCatalog status: pending → indexed / name_only / failed
```

- **File catalog** (`core/file_catalog.py`, SQLite): every file in every source, including
  photos, archives and installers. Powers instant fuzzy name search and change detection.
  A rescan of an unchanged tree reads no file contents at all.
- **Content index** (`core/vector_store.py`): one SQLite file holding the chunk rows, their
  384-dim embeddings in a [sqlite-vec](https://github.com/asg017/sqlite-vec) table
  (`BAAI/bge-small-en-v1.5` via ONNX/fastembed, no torch) and an FTS5 full-text table for
  BM25 keyword search. A writer and a reader connection in WAL mode let searches run while
  the index worker writes, and the reader memory-maps the file so vector scans stay in RAM.
- **Rules** (`core/index_rules.py`): per-folder "names only" vs "names + contents", file-type
  categories, size cap, default excludes (`node_modules`, `.git`, Office lock files…) and
  user globs.
- **Incremental by construction**: size+mtime skips unchanged files without reading them; a
  content hash then skips re-embedding when only the mtime changed.
- **Schema versioning**: changing the embedding model or row layout triggers a clean rebuild
  instead of mixing incompatible vectors.
- **Parsing**: PDFs use pdfium's text layer (fast); scanned PDFs fall back to the OCR engine
  built into Windows (`Windows.Media.Ocr`), so there's no OCR model to download or install;
  Office and Outlook formats go through MarkItDown with only those converters installed.

## 4. Retrieval

`core/retriever.py` runs vector search and BM25 keyword search in parallel and merges them
with **reciprocal rank fusion**. Vector search handles paraphrase ("vacation in Portugal" →
Lisbon notes); keyword search handles exact tokens that embeddings blur (`INV-2231`,
`MTR-88213-K`, surnames). RRF combines ranks rather than raw scores, so the two scoring scales
never have to be calibrated against each other.

`scripts/eval_retrieval.py` measures this on a labelled corpus:

| Strategy | recall@1 | recall@5 | MRR | ms/query |
|---|---|---|---|---|
| Vector only | 0.92 | 1.00 | 0.95 | 22 |
| Hybrid (vector + BM25, RRF) | 1.00 | 1.00 | 1.00 | 22 |

Keyword queries drop filler words ("what", "the", "does") and quote each remaining word, so
`INV-2231` matches that exact code, and a question doesn't make BM25 score the whole index.

At 20,000 chunks with a realistic word distribution, the SQLite store compared with the
LanceDB store it replaced in 2.1:

| | LanceDB (2.0) | SQLite + sqlite-vec + FTS5 (2.1) |
|---|---|---|
| Write 20k chunks | 45.2 s | 17.7 s |
| Vector search | 45 ms | 21 ms |
| Keyword search | 21 ms | 1.1 ms |

## 5. A chat turn

```
POST /chat {text, conversation_id?}
  │
  ├─ fast path? ("open X" with a ≥90 app match, "find report.pdf") ── answer, no model call
  │
  └─ Agent loop (max N steps)
       model.stream_chat(system, history, tool specs)
         ├─ text deltas ─────────────────────────────► SSE "token"
         └─ tool calls
              ├─ read-only tool → run → SSE "tool" chips → result back to the model
              └─ action tool (open/launch/write)
                   ├─ pre-approved in Settings → run
                   └─ otherwise → SSE "confirm" and pause the turn
                        POST /chat/{id}/confirm {call_id, approved, always_allow}
                        → run or record "declined" → continue the loop
```

- **Tools** (`tools/`): `search_files`, `find_files_by_name`, `list_recent_files`,
  `read_file`, `summarize_file`, `get_file_info`, `open_app`, `open_file`,
  `reveal_in_explorer`, `open_website`, `open_windows_setting`, `save_note`, `search_notes`,
  `system_status`.
- **Path guard**: every file tool resolves the path first (defeating `..` tricks) and refuses
  anything outside the user's shared folders or Nimbus's own notes folder.
- **Persistence**: every message, tool call and tool result is stored (SQLite), so a paused
  turn survives a restart and chats can be continued later.
- **Models without tool support** (some small Ollama models) fall back to a single
  retrieve-then-answer call.

## 6. Providers

`llm/provider.py` defines the contract (`complete`, `stream`, `stream_chat`, `list_models`,
`is_available`). Each backend converts the neutral `ChatMessage` / `ToolSpec` shapes to its own
wire format in a dedicated `*_messages.py` module. `llm/active_provider.py` is the single
object the rest of the app holds: it forwards to the current backend, swaps it when Settings
change, and enforces the optional daily call cap.

API keys are stored in Windows Credential Manager through `keyring`; they are never written
to `settings.json`, never returned by the API, and never logged.

## 7. Where data lives

| What | Where |
|---|---|
| Settings chosen in the UI | `%APPDATA%\Nimbus\settings.json` |
| API keys | Windows Credential Manager (service "Nimbus") |
| File catalog | `%APPDATA%\Nimbus\catalog.db` |
| Search index (chunks, vectors, full text) | `%APPDATA%\Nimbus\search.db` |
| Chats | `%APPDATA%\Nimbus\conversations.db` |
| Notes | `%APPDATA%\Nimbus\notes\*.md` |
| Embedding model cache | `%APPDATA%\Nimbus\models\` |
| Logs (rotating) | `%APPDATA%\Nimbus\logs\nimbus.log` |

Settings resolve in this order: Settings window → environment → `.env` (developer fallback).
Values from a 1.x `.env` are migrated automatically (`config/legacy_settings.py`).

## 8. Security notes

- The API binds to `127.0.0.1` only.
- Nimbus never modifies, moves or deletes user files; the only writes are its own notes.
- Launching apps, opening files/URLs and saving notes require an explicit click unless the
  user pre-approves that tool.
- Logs record paths, counts and durations — never file contents, prompts or keys.

## 9. Testing

`pytest -q` runs the whole suite offline: model SDKs, the OS credential store, the Win32
hotkey API, app launching and URL opening are all faked. Storage tests use real SQLite
databases (with sqlite-vec loaded) in temporary folders. CI (`.github/workflows/ci.yml`) runs lint and tests on Windows.
