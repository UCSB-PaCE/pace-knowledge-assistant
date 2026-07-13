# pace-knowledge-assistant

A Streamlit + MongoDB Atlas RAG chatbot that answers natural-language questions
over a collection of Zoho support tickets. Built for UCSB PaCE's **AI Symposium
2026** ("Building a Secure AI Knowledge Assistant with RAG").

> **Repo name note.** This project lives on GitHub as
> [`UCSB-PaCE/pace-knowledge-assistant`](https://github.com/UCSB-PaCE/pace-knowledge-assistant)
> (renamed from `pace-symposium2026` on 2026-07-09). The local working directory
> is still named `pace-symposium2026` (a file lock blocked the on-disk rename),
> so paths in this repo read `pace-symposium2026/...` while the remote is
> `pace-knowledge-assistant`.

---

## What it does

A user asks a plain-English question (for example, "Summarize tickets for the
last 10 days"). The app then:

1. **Parses intent.** `IntentExtractionAgent` (a LangChain chain backed by the
   internal LLM Sandbox API) turns the question into a structured
   `TicketQueryIntent`: `days`, `limit`, and `summary_type`.
2. **Embeds and retrieves.** The question is embedded with Voyage AI, and
   MongoDB Atlas Vector Search (`$vectorSearch`) pulls the most relevant ticket
   content.
3. **Generates the answer.** The retrieved tickets become context for a final
   prompt sent to the same LLM Sandbox API, which produces the answer shown in
   the UI.

---

## Stack

| Layer | Technology |
|-------|------------|
| UI | Streamlit (`app.py`) |
| Vector store | MongoDB Atlas + `pymongo`, `$vectorSearch` over a 1024-dimension cosine index |
| Embeddings | Voyage AI (`voyageai` SDK, model `voyage-4`) |
| Intent extraction | LangChain-core (`PromptTemplate` / `JsonOutputParser` / `LLM` base) + Pydantic (`TicketQueryIntent`) |
| LLM transport | Internal "LLM Sandbox" conversation API via a custom `SandBoxLLM` wrapper (`requests`) |
| Config | `python-dotenv` (`.env`) |

Python 3. No build step, no CI, no test suite, no deployment/hosting config
(no Dockerfile, Procfile, or `.streamlit/config.toml`) at this time.

---

## Files and entry points

| File | Role |
|------|------|
| `app.py` | Minimal Streamlit chat UI. Run with `streamlit run app.py`. Title reads "Zoho Tickets Chatbot!". Calls `intent_agent.extract()` first (to show detected filters), then `ZohoTicket.ask()`. |
| `zohoai_app.py` | Richer "Zoho Tickets AI" Streamlit UI (styled chat, sidebar, persistent chat sessions). Run with `streamlit run zohoai_app.py`. Shares the same `ZohoTicket` backend via `chatbot.ask()`. See the hardcoded-history-path quirk below. |
| `mongodb_RAG.py` | `ZohoTicket` class: the RAG orchestrator. Holds the MongoDB client, the Voyage client, and the `SandBoxLLM` client; implements `get_embedding`, `get_query_results` (the `$vectorSearch` pipeline), and `ask`. |
| `intent_agent.py` | `IntentExtractionAgent` + the `TicketQueryIntent` Pydantic schema. **Runs on every question before the RAG call.** See the silent-fallback note below. |
| `llm_agent.py` | `SandBoxLLM`: the LLM Sandbox transport. Async create-conversation then adaptive-backoff polling. `AdaptivePollingConfig` (default `max_retries=5`, `0.3s` initial interval backing off `1.5x` to a `5s` ceiling). |
| `vector-index.py` | One-off CLI script that **provisions the Atlas Search vector index** (`vector_index`) the whole pipeline depends on. Run once before first use: `python vector-index.py`. The filename has a hyphen, so it is a script, not an importable module. |
| `mongodb_RAG.ipynb` | Exploration notebook (outputs stripped in git). |
| `.env.example` | Template for the required secrets (see below). |

---

## External surfaces and auth

All credentials are read from `.env` (see `.env.example`). Key **names** only:

| Surface | Env var(s) | Auth | Notes |
|---------|-----------|------|-------|
| MongoDB Atlas | `MongoDB_Client` | connection string with embedded user/password | Database `zendesk_ticket`, collection `Zoho_Ticket`. |
| Voyage AI | `VOYAGE_API_KEY` | API key | Embedding model `voyage-4`, 1024-dim. |
| LLM Sandbox conversation API | `LLMSANDBOX_API_ENDPOINT`, `LLMSANDBOX_API_KEY` | `x-api-key` header | Internal AWS API Gateway-backed conversation service. Used for both intent extraction and final answer generation. Optional tuning knobs: `LLMSANDBOX_POLL_INITIAL_MS`, `LLMSANDBOX_POLL_BACKOFF_FACTOR`, `LLMSANDBOX_POLL_MAX_MS`, `LLMSANDBOX_POLL_MAX_RETRIES`, `LLMSANDBOX_REQUEST_TIMEOUT_SECONDS`. |

`.env` is gitignored; only `.env.example` is tracked. Never commit real values.

---

## Run it

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure secrets
cp .env.example .env          # then fill in the real values

# 4. Provision the Atlas vector index (run once)
python vector-index.py

# 5. Launch a chat UI (two are available)
streamlit run app.py          # minimal UI
# streamlit run zohoai_app.py # richer UI with sidebar + chat history
```

There is no automated test suite; verification is manual through the Streamlit UI.

---

## Known quirks

These are documented so the next contributor is not surprised by them. None are
fixed here.

- **Intent extraction fails silently.** `IntentExtractionAgent.extract()` wraps
  the entire chain in `try/except Exception`. On any failure (network,
  JSON-parse, or Pydantic validation) it `print()`s "Intent extraction failed:
  ..., using defaults." and returns a default `TicketQueryIntent`
  (`days=10`, `limit=10`, `summary_type='general'`). The Streamlit "Filters
  detected" expander then shows those defaults with no indication that the
  user's actual request (a specific date range or ticket count) was dropped.
- **`days` is not actually applied to retrieval.** `get_query_results` hardcodes
  the vector-search date filter to the last 10 days regardless of `intent.days`.
  `intent.days` only appears in the answer prompt text, so a "last 30 days"
  request retrieves 10 days of tickets while the prompt claims 30. `intent.limit`
  and `intent.summary_type` are honored.
- **Zoho vs Zendesk naming.** The UI and labels say "Zoho", but the MongoDB
  database/collection is `zendesk_ticket.Zoho_Ticket`. This is a leftover from an
  earlier prototype name, not two data sources.
- **`program` filter is disabled.** The program-based filtering is commented out
  in `mongodb_RAG.py` / `intent_agent.py`, though `vector-index.py` still declares
  a `program` filter field on the index.
- **Unpinned dependencies.** `requirements.txt` pins no versions and lists
  `pandas` and `sentence-transformers`, neither of which is imported by the
  tracked source.
- **Default model string.** `SandBoxLLM.model` defaults to `"claude-v4.5-sonnet"`
  and is overridable when constructing the client.
- **`zohoai_app.py` hardcodes a chat-history path.** Its `HISTORY_FILE` points at
  an absolute macOS path under one contributor's home directory, so persistent
  chat history will not work on another machine without editing that line.

---

## Repo conventions

Identity, commit, and issue rules live in [`CLAUDE.md`](CLAUDE.md).
