# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Local English vocabulary tool: paste an English sentence → Gemini translates it and surfaces 2–5 key words **or fixed phrases** (phrasal verbs, idioms, collocations) with usage and example → user clicks any other word, or drag-selects a run of words, to look it up on demand → save chosen words/phrases to a SQLite vocabulary notebook (search / edit / delete). FastAPI backend, vanilla HTML/JS frontend, no build step.

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
1. **translate_sentence(sentence)** — 一次调用同时返回：整句翻译 + AI 默认推荐的 2–5 个关键词/固定词组（每个含词性 / 本句含义 / 通用含义 / 例句 / 难度）。`word` 字段要求逐字匹配原句（词组含中间空格），供后端定位 token 范围；`pos` 对词组用 phrasal verb/idiom/collocation
2. **lookup_word(word, sentence, translation)** — 用户手动点击单词或拖选词组时触发，针对该单词/词组在给定上下文中生成同一 `KeyWord` 结构

### Tokenization & phrase matching (`app/routers/translate.py`)
后端用一行正则把原句切成 token 列表（`is_word` 标记单词 vs 标点空格），不走 LLM，前端据此渲染可点击的句子。
`_find_phrase_range(tokens, phrase)` 把 Gemini 返回的 `key_words[].word`（可能是词组）在 word-token 序列中做逐词、大小写不敏感的连续匹配，找到后把 `[start_idx, end_idx]`（`tokens` 的闭区间下标）写回 `TranslatedKeyWord`；找不到则为 `None`（该词/词组仍会显示为卡片，只是原句里不高亮——多见于 Gemini 改写了措辞/时态的情况）。这两个字段只存在于 `/api/translate` 响应里，不出现在 Gemini 的 `response_schema`（避免让模型误填）。

### Phrase lookup (frontend, `app/static/app.js`)
- AI 高亮：`aiKeyWords` 里每个词/词组按其 `[start_idx, end_idx]` 覆盖的 token（含中间的空格/标点 token）整体加下划线，用 `chalk-N`（N = key word 在数组里的下标 mod 3）保证同一词组下划线颜色首尾一致，且和对应卡片顶部色条一致
- 手动查词组：监听 `selectionchange`，当用户在原句里拖选出跨空格的文本时，在选区上方弹出「🔍 查询 "..."」按钮，点击后按选中文本调用 `/api/lookup`（与单词点击共用同一 popover 渲染逻辑）

### Storage (`app/services/db.py`)
纯 stdlib `sqlite3`，无 ORM。`vocab` 表 + `UNIQUE(word, pos)` 防重。

### API Layer
- `POST /api/translate` — 接收 `{sentence}`，返回翻译 + tokens + key_words
- `POST /api/lookup` — 接收 `{word, sentence, translation}`，返回单个词条
- `POST /api/vocab` / `GET /api/vocab` / `PUT /api/vocab/{id}` / `DELETE /api/vocab/{id}` — 单词本 CRUD

### Frontend (`app/static/`)
纯 HTML/CSS/JS，无构建步骤。双 tab：翻译 / 单词本。翻译结果中原句以可点击 token 渲染，AI 推荐词高亮；点击未高亮词触发 lookup popover。

#### 视觉设计：黑板笔记本主题
`style.css` 是"黑板 + 彩色粉笔"视觉体系，围绕"英语学习笔记本"这个主题设计，刻意避开常见的"暖白+衬线+赭石"或"近黑+单一荧光色"AI 模板化配色：

- **配色**（`:root` 变量）：深板绿 `--board`/`--panel` 做底，粉笔白 `--chalk` 做正文，四种"粉笔色"各司其职——黄 `--chalk-yellow`（AI 推荐词高亮 / 激活态）、蓝 `--chalk-blue`（交互 / 焦点）、粉 `--chalk-pink`（危险操作）、绿 `--chalk-green`（成功态）
- **字体**：标题、tab 名、"关键词"等分区标签用 Google Fonts 的 `Schoolbell`（手写粉笔体，需联网加载，走 CDN `<link>`，不影响离线运行本身）；正文保持系统 sans 栈（中文场景需要）；词性/难度标签等"字典注释"用等宽字体
- **签名元素**：原句中 AI 推荐词/词组的下划线用内联 SVG data-URI 画成手绘波浪线，按 `chalk-0/1/2` class（黄/蓝/粉）轮换，模拟老师用不同颜色粉笔逐词/逐词组标注；单词卡片轻微倾斜 + 虚线边框，像贴在黑板上的小卡片
- **已知修复**：`.status` / `.pager` 原先直接写死 `display: flex`，会覆盖浏览器 `[hidden] { display: none }` 的默认规则，导致"分析中…"提示框和分页条即使被 JS 设置 `hidden` 也不会消失。改用 `.foo:not([hidden]) { display: flex; ... }` 的写法后修复——这类 class 里显式声明 `display` 且元素又用 `hidden` 属性做显隐控制时，都要留意这个坑

## Key Design Decisions

- **google-genai SDK + Pydantic response_schema**：让 SDK 完成 JSON 校验，无需手动解析
- **Python 3.11**：与本机环境一致
- **No ORM**：CRUD 简单，stdlib `sqlite3` 足够
- **Tokenization in backend, not LLM**：分词是确定性的，没必要花 LLM token
- **Lookup cache on frontend**：同一个词二次点击不重复调 API
