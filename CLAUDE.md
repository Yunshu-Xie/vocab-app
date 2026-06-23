# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Local English vocabulary tool: paste an English sentence → Gemini translates it and surfaces 2–5 key words with usage and example → user clicks any other word in the sentence to look it up on demand → save chosen words to a SQLite vocabulary notebook (search / edit / delete). FastAPI backend, vanilla HTML/JS frontend, no build step.

## Common Commands

```bash
# Install dependencies
pip install -e .[dev]

# Run the development server
uvicorn app.main:app --reload

# Run all tests
pytest

# Run a single test file / specific test
pytest tests/test_db.py -v
pytest tests/test_api.py::test_translate_success -v

# Linting
ruff check .
ruff format .
```

## Configuration

`.env` 中需要配置：
- `GEMINI_API_KEY` — Google AI Studio 申请的 API Key（https://aistudio.google.com/apikey）
- `GEMINI_MODEL` — 使用的模型（默认 `gemini-2.5-flash-lite`，免费 1000 RPD）
- `DB_PATH` — SQLite 数据库文件路径（默认 `vocab.db`）

`app/config.py` 通过 pydantic-settings 读取 `.env`。

## Architecture

### AI Pipeline (`app/services/gemini.py`)
通过 `google-genai` SDK 调用 Gemini，用 `response_schema` 强制结构化输出：
1. **translate_sentence(sentence)** — 一次调用同时返回：整句翻译 + AI 默认推荐的 2–5 个关键词（每个含词性 / 本句含义 / 通用含义 / 例句 / 难度）
2. **lookup_word(word, sentence, translation)** — 用户手动点击非默认词时触发，针对单词在给定上下文中生成同一 `KeyWord` 结构

### Tokenization (`app/routers/translate.py`)
后端用一行正则把原句切成 token 列表（`is_word` 标记单词 vs 标点空格），不走 LLM，前端据此渲染可点击的句子。

### Storage (`app/services/db.py`)
纯 stdlib `sqlite3`，无 ORM。`vocab` 表 + `UNIQUE(word, pos)` 防重。

### API Layer
- `POST /api/translate` — 接收 `{sentence}`，返回翻译 + tokens + key_words
- `POST /api/lookup` — 接收 `{word, sentence, translation}`，返回单个词条
- `POST /api/vocab` / `GET /api/vocab` / `PUT /api/vocab/{id}` / `DELETE /api/vocab/{id}` — 单词本 CRUD

### Frontend (`app/static/`)
纯 HTML/CSS/JS，无构建步骤。双 tab：翻译 / 单词本。翻译结果中原句以可点击 token 渲染，AI 推荐词高亮；点击未高亮词触发 lookup popover。

## Key Design Decisions

- **google-genai SDK + Pydantic response_schema**：让 SDK 完成 JSON 校验，无需手动解析
- **Python 3.11**：与本机环境一致
- **No ORM**：CRUD 简单，stdlib `sqlite3` 足够
- **Tokenization in backend, not LLM**：分词是确定性的，没必要花 LLM token
- **Lookup cache on frontend**：同一个词二次点击不重复调 API
