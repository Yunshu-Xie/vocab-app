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

### Tokenization & phrase matching (`app/services/tokenize.py`)
纯文本逻辑（不走 LLM），独立于 HTTP 层，router 和测试都走公开接口：
- `tokenize(sentence)` 用一行正则把原句切成 token 列表（`is_word` 标记单词 vs 标点空格），前端据此渲染可点击的句子
- `find_phrase_range(tokens, phrase)` 把 Gemini 返回的 `key_words[].word`（可能是词组）在 word-token 序列中做逐词、大小写不敏感的连续匹配（词组自身也用 `tokenize` 切词，保证"什么算一个词"只有一处定义），找到后把 `[start_idx, end_idx]`（`tokens` 的闭区间下标）写回 `TranslatedKeyWord`；找不到则为 `None`（该词/词组仍会显示为卡片，只是原句里不高亮——多见于 Gemini 改写了措辞/时态的情况）。这两个字段只存在于 `/api/translate` 响应里，不出现在 Gemini 的 `response_schema`（避免让模型误填）。

### Phrase lookup (frontend, `app/static/app.js`)
- AI 高亮：`aiKeyWords` 里每个词/词组按其 `[start_idx, end_idx]` 覆盖的 token（含中间的空格/标点 token）整体加下划线，用 `chalk-N`（N = key word 在数组里的下标 mod 3）保证同一词组下划线颜色首尾一致，且和对应卡片顶部色条一致
- 手动查词组：监听 `selectionchange`，当用户在原句里拖选出跨空格的文本时，在选区上方弹出「🔍 查询 "..."」按钮，点击后按选中文本调用 `/api/lookup`（与单词点击共用同一 popover 渲染逻辑）

### Storage (`app/services/db.py`)
纯 stdlib `sqlite3`，无 ORM。`vocab` 表（词条本身：word/lemma/pos/meaning/example/notes）+ `UNIQUE(word, pos)` 防重；`vocab_usage` 表（`vocab_id` 外键 + `ON DELETE CASCADE`）一对多，是"在哪些句子里遇到过这个词"的**唯一**归属地——`vocab` 表上没有 source_sentence/source_translation 列，`VocabCreate` 里的这两个字段只作为 usage 记录的输入。

**重复添加 = 合并用法，不是报错**：写入的唯一入口是 `upsert_vocab(data) -> (row, created)`，单事务内完成"(word, pos) 不存在则插入词条 + 无条件记录本次例句"。例句去重由 schema 层的 `UNIQUE(vocab_id, source_sentence)` 索引 + `INSERT OR IGNORE` 保证（原子，且对所有写入方生效），不是应用层 SELECT-then-INSERT。router 里 `create_vocab` 只做一件事：`created` 为 False 时把 201 降为 200。首次插入时创建例句就是 usage #1，所以 `VocabResponse.usages` 从第一次插入起就是完整历史。

### API Layer
- `POST /api/translate` — 接收 `{sentence}`，返回翻译 + tokens + key_words
- `POST /api/lookup` — 接收 `{word, sentence, translation}`，返回单个词条
- `POST /api/vocab` / `GET /api/vocab` / `PUT /api/vocab/{id}` / `DELETE /api/vocab/{id}` — 单词本 CRUD；响应体里的 `usages: VocabUsage[]` 是该词全部遇到过的例句历史（按时间正序）

### Frontend (`app/static/`)
纯 HTML/CSS/JS，无构建步骤。双 tab：翻译 / 单词本。翻译结果中原句以可点击 token 渲染，AI 推荐词高亮；点击未高亮词触发 lookup popover。单词本每条卡片展示 `usages`：默认展开前 2 条，多出的收进「+N more」折叠按钮（`buildUsagesBlock`）。

#### 视觉设计：黑板笔记本主题
`style.css` 是"黑板 + 彩色粉笔"视觉体系，围绕"英语学习笔记本"这个主题设计，刻意避开常见的"暖白+衬线+赭石"或"近黑+单一荧光色"AI 模板化配色：

- **配色**（`:root` 变量）：深板绿 `--board`/`--panel` 做底，粉笔白 `--chalk` 做正文，四种"粉笔色"各司其职——黄 `--chalk-yellow`（AI 推荐词高亮 / 激活态）、蓝 `--chalk-blue`（交互 / 焦点）、粉 `--chalk-pink`（危险操作）、绿 `--chalk-green`（成功态）
- **字体**：标题、tab 名、"关键词"等分区标签用 Google Fonts 的 `Schoolbell`（手写粉笔体，需联网加载，走 CDN `<link>`，不影响离线运行本身）；正文保持系统 sans 栈（中文场景需要）；词性/难度标签等"字典注释"用等宽字体
- **签名元素**：原句中 AI 推荐词/词组的下划线是手绘波浪线——一个颜色无关的 SVG data-URI 作为 `mask`，套在 `currentColor` 填充的 `::before` 条上，所以波浪形状只定义一次、颜色自动跟随文字（加入单词本后整体变绿）。颜色映射只有一处：`.chalk-0/1/2 { --chalk-color: ... }`（黄/蓝/粉），下划线和卡片顶部色条都消费 `var(--chalk-color)`；JS 侧对应 `chalkClass(kwIdx)`（`CHALK_COLOR_COUNT` 必须和 CSS 里的 `.chalk-N` 数量一致）。单词卡片轻微倾斜 + 虚线边框，像贴在黑板上的小卡片
- **`[hidden]` 全局规则**：样式表顶部有 `[hidden] { display: none !important; }`，保证 JS 用 `hidden` 属性做显隐时不会被任何 class 里的 `display` 声明覆盖——新组件直接写 `display: flex/grid` 即可，不需要 `:not([hidden])` 之类的规避写法

## Key Design Decisions

- **google-genai SDK + Pydantic response_schema**：让 SDK 完成 JSON 校验，无需手动解析
- **Python 3.11**：与本机环境一致
- **No ORM**：CRUD 简单，stdlib `sqlite3` 足够
- **Tokenization in backend, not LLM**：分词是确定性的，没必要花 LLM token
- **Lookup cache on frontend**：同一个词二次点击不重复调 API
