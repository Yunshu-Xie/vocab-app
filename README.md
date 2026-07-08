# vocab-app

A local English learning tool: paste a sentence, get a translation plus 2–5 AI-picked key words **or fixed phrases** (phrasal verbs, idioms, collocations) with context-aware definitions. Click any other word — or drag-select a run of words — to look it up on demand. Save what you want to a local SQLite notebook; re-adding a known word from a new sentence grows its usage history instead of being rejected.

Built with FastAPI, vanilla HTML/JS (no build step), SQLite (no ORM), and Gemini 2.5 Flash-Lite for translation and lookup.

## Features

- **Sentence translation** — paste English, get a concise Chinese translation
- **AI key-word / phrase picking** — Gemini surfaces 2–5 worth-studying words *or fixed phrases* (B1+), each with part of speech, contextual meaning, dictionary meaning, example sentence, and CEFR difficulty. Multi-word phrases get one continuous underline in the rendered sentence, colored to match their card
- **Click-to-look-up any word, drag-select any phrase** — every word is clickable for an on-demand lookup popover (cached per word); drag-selecting 2+ words pops up a "look up phrase" button for anything the AI didn't pick
- **Override AI picks** — dismiss any default key word with a single click
- **Local notebook with usage history** — save words/phrases to SQLite; meeting a known word again appends the new sentence as another usage record instead of erroring, shown as an expandable list per entry
- **User-safe error messages** — Gemini/SDK failures (rate limits, bad key, transient outages) are classified into a handful of fixed, actionable messages server-side; raw exception text never reaches the browser. Retryable failures (e.g. temporary overload) show a one-click retry; non-retryable ones (bad key, quota exhausted) don't

## Why Gemini 2.5 Flash-Lite?

It's free at the scale a single user needs (1000 requests per day) and ranks at the top for English-language understanding among free-tier LLMs. The integration uses `google-genai` with a Pydantic `response_schema`, so the model is forced into a typed JSON shape — no fragile string parsing.

## Quick start

```bash
git clone https://github.com/Yunshu-Xie/vocab-app.git
cd vocab-app

python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'

cp .env.example .env
# Edit .env and paste your key from https://aistudio.google.com/apikey

.venv/bin/uvicorn app.main:app --reload
# Open http://localhost:8000
```

## Configuration

`.env` reads three variables (see `.env.example`):

| Var | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | _(required)_ | Google AI Studio API key |
| `GEMINI_MODEL` | `gemini-2.5-flash-lite` | Model name |
| `DB_PATH` | `vocab.db` | SQLite file path |

## Architecture

```
app/
├── config.py              # pydantic-settings, reads .env
├── main.py                # FastAPI + lifespan(init_db) + static mount
├── models/schemas.py      # Pydantic request/response shapes + Gemini response_schema
├── routers/
│   ├── translate.py       # POST /api/translate, POST /api/lookup
│   └── vocab.py           # CRUD /api/vocab
├── services/
│   ├── gemini.py          # google-genai wrapper, structured output, error classification
│   ├── tokenize.py        # regex tokenizer + phrase locating (no LLM)
│   └── db.py              # stdlib sqlite3 wrapper, no ORM
└── static/                # vanilla HTML/CSS/JS, no build step — chalkboard/chalk visual theme
```

### Translation flow

1. Front-end `POST /api/translate { sentence }`
2. Back-end calls Gemini once with a Pydantic schema — returns `{ translation, key_words[] }`, where each key word may be a single word or a fixed phrase
3. Back-end tokenizes the sentence with a regex (no LLM cost) and locates each key word's token span (`start_idx`/`end_idx`) so multi-word phrases can be underlined as one continuous run
4. Front-end renders the sentence as clickable spans; AI-picked words/phrases are highlighted in one of three chalk colors, matching their card below

### Look-up flow

- Click a highlighted word/phrase → scroll to its existing card
- Click a plain word → popover with a loading spinner → `POST /api/lookup { word, sentence, translation }` → Gemini returns a single `KeyWord` → rendered in the popover
- Drag-select 2+ words → a "🔍 查询" button appears above the selection → same `/api/lookup` call, same popover
- Each lookup is cached in memory per session; failed lookups that were retryable show a retry button

### Vocab notebook flow

- `POST /api/vocab` creates a new entry (`201`), or — if `(word, pos)` already exists — appends the sentence as a new usage record and returns the merged entry (`200`) instead of rejecting it. Re-adding the exact same sentence is a no-op
- Each entry's `usages[]` is its full encounter history (sentence + translation + timestamp), shown in the notebook tab as the first 2 with a "+N more" expand toggle

## API

| Method | Path | Body | Returns |
|---|---|---|---|
| `POST` | `/api/translate` | `{ sentence }` | `{ translation, tokens[], key_words[] }` — each key word includes `start_idx`/`end_idx` into `tokens` |
| `POST` | `/api/lookup` | `{ word, sentence, translation }` | `KeyWord` (word can be a phrase) |
| `POST` | `/api/vocab` | `VocabCreate` | `VocabResponse` — `201` if newly created, `200` if merged into an existing entry's usage history |
| `GET` | `/api/vocab?q=&page=&limit=` | — | `{ items[], total, page, limit }` |
| `GET` | `/api/vocab/{id}` | — | `VocabResponse` |
| `PUT` | `/api/vocab/{id}` | `VocabUpdate` (partial) | `VocabResponse` |
| `DELETE` | `/api/vocab/{id}` | — | 204 |

`VocabResponse` includes `usages: [{ source_sentence, source_translation, created_at }]` — the full history of sentences this word/phrase was saved from.

Gemini failures return `502` with `{ "detail": { "message": "...", "retryable": true|false } }` — never raw SDK/network error text.

## Development

```bash
pytest          # 38 tests, all mocked — does not call Gemini
ruff check .
ruff format .
```

Tests use a per-test temporary SQLite DB and mock `app.routers.translate.translate_sentence` / `lookup_word`. No network calls.

## Key design decisions

- **google-genai SDK + Pydantic `response_schema`** — the SDK validates the JSON shape, so there's no fragile manual parsing
- **No ORM** — CRUD is simple, so stdlib `sqlite3` is enough; `UNIQUE(word, pos)` handles word dedup, `UNIQUE(vocab_id, source_sentence)` handles usage dedup
- **Tokenization in the backend, not the LLM** — splitting a sentence into clickable tokens (and locating phrases within it) is deterministic, so it's a regex in `app/services/tokenize.py`, not an LLM call
- **Duplicate add = merge, not reject** — `db.upsert_vocab` inserts-or-appends-usage in one transaction; the router just maps `created` to `201`/`200`
- **User-facing error messages are a fixed, small set** — Gemini/SDK errors are classified by structured status/code (never by interpolating the raw exception) into actionable Chinese messages with a `retryable` flag, so the frontend can offer a one-click retry only when it would actually help
- **Front-end lookup cache** — re-clicking the same word reuses the cached result instead of calling the API again
- **Python 3.11+** — matches the local environment (tested on 3.12)

## License

MIT
