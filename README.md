# vocab-app

A local English learning tool: paste a sentence, get a translation plus 2–5 AI-picked key words with context-aware definitions, click any other word in the sentence to look it up on demand, and save your favorites to a local SQLite notebook with search / edit / delete.

Built with FastAPI, vanilla HTML/JS (no build step), SQLite (no ORM), and Gemini 2.5 Flash-Lite for both translation and per-word lookup.

## Features

- **Sentence translation** — paste English, get a concise Chinese translation
- **AI key-word picking** — Gemini surfaces the 2–5 most worth-studying words (B1+), with part of speech, contextual meaning, dictionary meaning, example sentence, and CEFR difficulty
- **Click-to-look-up any word** — every word in the sentence is clickable; non-default words trigger an on-demand lookup popover (cached per word so re-clicks are free)
- **Override AI picks** — dismiss any default key word with a single click
- **Local notebook** — save chosen words to SQLite with `UNIQUE(word, pos)` deduplication; search, edit notes, delete

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
│   ├── gemini.py          # google-genai wrapper, structured output
│   └── db.py              # stdlib sqlite3 wrapper, no ORM
└── static/                # vanilla HTML/CSS/JS, no build step
```

### Translation flow

1. Front-end `POST /api/translate { sentence }`
2. Back-end calls Gemini once with a Pydantic schema — returns `{ translation, key_words[] }`
3. Back-end runs a regex tokenizer on the sentence (no LLM cost) and merges tokens into the response
4. Front-end renders the sentence as clickable spans; AI-picked words are highlighted

### Click-to-look-up flow

- Click a highlighted word → scroll to its existing card
- Click a plain word → popover with a loading spinner → `POST /api/lookup { word, sentence, translation }` → Gemini returns a single `KeyWord` → rendered in the popover
- Each word's lookup is cached in memory per session

## API

| Method | Path | Body | Returns |
|---|---|---|---|
| `POST` | `/api/translate` | `{ sentence }` | `{ translation, tokens[], key_words[] }` |
| `POST` | `/api/lookup` | `{ word, sentence, translation }` | `KeyWord` |
| `POST` | `/api/vocab` | `VocabCreate` | `VocabResponse` (201), or 409 with `existing_id` |
| `GET` | `/api/vocab?q=&page=&limit=` | — | `{ items[], total, page, limit }` |
| `GET` | `/api/vocab/{id}` | — | `VocabResponse` |
| `PUT` | `/api/vocab/{id}` | `VocabUpdate` (partial) | `VocabResponse` |
| `DELETE` | `/api/vocab/{id}` | — | 204 |

## Development

```bash
pytest          # 23 tests, all mocked — does not call Gemini
ruff check .
ruff format .
```

Tests use a per-test temporary SQLite DB and mock `app.routers.translate.translate_sentence` / `lookup_word`. No network calls.

## License

MIT
