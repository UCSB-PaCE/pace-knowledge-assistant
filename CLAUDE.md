# CLAUDE.md - pace-knowledge-assistant

Guidance for Claude Code working in this repository. These instructions apply to
this repo specifically; the umbrella PaCERepo `CLAUDE.md` / `ROUTING.md` still
govern cross-repo orchestration.

## Repo identity

- **GitHub remote:** `UCSB-PaCE/pace-knowledge-assistant` (public). Renamed from
  `pace-symposium2026` on 2026-07-09.
- **Local directory:** still `pace-symposium2026` (a file lock blocked the on-disk
  rename). Work in `d:/agent_coding_container/PaCERepo/pace-symposium2026`, but
  commit and push to `UCSB-PaCE/pace-knowledge-assistant`.
- **Purpose:** a Streamlit + MongoDB Atlas RAG chatbot over Zoho support tickets,
  built for UCSB PaCE's AI Symposium 2026 ("Building a Secure AI Knowledge
  Assistant with RAG"). It is a prototype: no CI, no tests, no deployment config.

## Architecture

Question flow (all in-process, no MCP server, no backend service of its own):

```
user question
  -> IntentExtractionAgent.extract()        # intent_agent.py, LLM Sandbox
       -> TicketQueryIntent(days, limit, summary_type)
  -> ZohoTicket.get_embedding()             # Voyage AI, voyage-4
  -> MongoDB Atlas $vectorSearch            # mongodb_RAG.py, 1024-dim cosine
  -> final prompt to SandBoxLLM             # llm_agent.py, LLM Sandbox
  -> answer rendered in Streamlit           # app.py
```

Key modules:

- `app.py` - Minimal Streamlit UI. Entry point: `streamlit run app.py`. Calls
  `chatbot.intent_agent.extract(question)` (to display detected filters), then
  `chatbot.ask(question)`.
- `zohoai_app.py` - Alternate, richer Streamlit UI ("Zoho Tickets AI") with a
  sidebar and persistent chat sessions. Entry point: `streamlit run zohoai_app.py`.
  Same `ZohoTicket` backend. Note it hardcodes `HISTORY_FILE` to an absolute
  macOS path under a contributor's home directory (not portable as-is).
- `mongodb_RAG.py` - `ZohoTicket` orchestrator. Owns the MongoDB, Voyage, and
  `SandBoxLLM` clients. Database `zendesk_ticket`, collection `Zoho_Ticket`.
- `intent_agent.py` - `IntentExtractionAgent` and the `TicketQueryIntent`
  Pydantic schema. Runs before every RAG call.
- `llm_agent.py` - `SandBoxLLM`, the LLM Sandbox transport with adaptive-backoff
  polling (`AdaptivePollingConfig`, `max_retries=5` default).
- `vector-index.py` - one-off script that provisions the Atlas Search vector
  index (`vector_index`). Run once with `python vector-index.py` before first
  use. Hyphen in the filename means it is a script, not an importable module.

## External surfaces and auth (names only, never values)

- **MongoDB Atlas** - `MongoDB_Client` (connection string with embedded
  user/password).
- **Voyage AI** - `VOYAGE_API_KEY` (embeddings, `voyage-4`).
- **LLM Sandbox conversation API** - `LLMSANDBOX_API_ENDPOINT`,
  `LLMSANDBOX_API_KEY`. Auth is the `x-api-key` header against an internal AWS
  API Gateway-backed conversation service. Used for both intent extraction and
  answer generation. Optional polling overrides: `LLMSANDBOX_POLL_INITIAL_MS`,
  `LLMSANDBOX_POLL_BACKOFF_FACTOR`, `LLMSANDBOX_POLL_MAX_MS`,
  `LLMSANDBOX_POLL_MAX_RETRIES`, `LLMSANDBOX_REQUEST_TIMEOUT_SECONDS`.

All secrets load from `.env`; only `.env.example` is tracked. `.env` and
`.env.*` are gitignored. A gitleaks pre-commit hook and `nbstripout` (for the
notebook) are configured via `.pre-commit-config.yaml`; run
`pip install pre-commit && pre-commit install` after cloning.

## Gotchas (verified in source, not yet fixed)

- **Silent intent fallback.** `IntentExtractionAgent.extract()` catches all
  exceptions and returns default filters (`days=10`, `limit=10`,
  `summary_type='general'`), only `print()`-ing the error. The UI shows the
  default filters with no signal that extraction failed, so a specific
  user request can be silently ignored. Surface this in the UI if you touch it.
- **`days` is ignored at retrieval time.** `get_query_results` in `mongodb_RAG.py`
  hardcodes the date filter to the last 10 days regardless of `intent.days`;
  `intent.days` only appears in the answer prompt text. `intent.limit` and
  `intent.summary_type` are honored.
- **Zoho vs Zendesk naming.** UI says "Zoho"; MongoDB names are
  `zendesk_ticket.Zoho_Ticket`. Prototype-era naming, one data source.
- **`program` filter disabled.** Commented out in code, though the index in
  `vector-index.py` still declares a `program` filter field.
- **Unpinned deps.** `requirements.txt` has no version pins and lists `pandas`
  and `sentence-transformers`, which are not imported by the tracked source.

## Git and identity

- **Identity is always `jengeln <j_engeln@ucsb.edu>`**, never the personal
  `Tamok` account. Verify `git config user.name/user.email` before committing,
  and `gh auth switch --user jengeln` if using `gh`.
- **Commit and push to `UCSB-PaCE/pace-knowledge-assistant`.**
- **Conventional Commits** (`feat`, `fix`, `docs`, `chore`, `refactor`, `test`,
  `build`, `ci`).
- **No em dashes** in outward-facing text (README, issue bodies, public content).
- Trunk-based: this repo works on `main`.

## Issues and project board

Issues are tracked on GitHub **Project #3** in the **UCSB-PaCE** org. File issues
in this repo and add them to Project #3 with all required fields (Assignee
`jengeln`, Issue Type, Status, Priority, Size, Labels). Dedup first. Full field
IDs and the create recipe are in the umbrella `CLAUDE.md` / `ROUTING.md`.

Labels for this repo use the canonical bare scheme plus the repo-specific `RAG`
label. Typical set: type `enhancement`, area `ai`, and `RAG`. The old
`symposium` label was retired on 2026-07-09 (the repo rename); do not reapply it.
