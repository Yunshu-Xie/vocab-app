from __future__ import annotations

import json
import logging
from typing import Optional

from google import genai
from google.genai import types

from app.config import settings
from app.models.schemas import KeyWord, TranslationPayload

logger = logging.getLogger(__name__)

_TRANSLATE_SYSTEM_PROMPT = """你是一个英语学习助手。给定一句英文，请：

1. 给出简洁、地道的中文翻译。
2. 从句中挑选 2-5 个有学习价值的词放入 key_words：
   - 难度在 CEFR B1 及以上（即学术或较少见的词、固定搭配的核心动词、形容词等）
   - 跳过 the / a / is / have / I / you 等极常见词
   - 每个词都要按 schema 给出：
     - word（原句中形式）
     - lemma（词典原形）
     - pos（词性英文：noun/verb/adjective/adverb 等）
     - meaning_in_context（本句中的中文含义）
     - general_meaning（该词常见的中文释义）
     - example（一句独立英文例句，不要复制原句）
     - difficulty（A1/A2/B1/B2/C1/C2 之一）

严格按照 response_schema 输出 JSON，不要附加解释。
"""

_LOOKUP_SYSTEM_PROMPT = """你是一个英语学习助手。
用户从下面这句英文里挑出一个特定单词，请只为该单词输出一条词条：

- word：用户挑选的单词（保留其在句中的形式）
- lemma：词典原形
- pos：词性英文，如 noun/verb/adjective/adverb
- meaning_in_context：该词在本句中的中文含义（结合上下文，不要泛泛而谈）
- general_meaning：该词常见的中文释义
- example：一句独立的英文例句，不可与原句相同
- difficulty：CEFR 难度等级 A1/A2/B1/B2/C1/C2 之一

严格按照 response_schema 输出 JSON，不要附加解释。
"""


_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise GeminiError("GEMINI_API_KEY 未配置，请在 .env 中填入")
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


class GeminiError(RuntimeError):
    """Wrap any Gemini SDK / network / parse failure."""


def _generate(
    *,
    system_prompt: str,
    user_text: str,
    schema_model: type,
) -> dict:
    client = _get_client()
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type="application/json",
        response_schema=schema_model,
    )
    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=user_text,
            config=config,
        )
    except Exception as exc:
        logger.exception("Gemini API call failed")
        raise GeminiError(f"Gemini API 调用失败：{exc}") from exc

    raw = response.text or ""
    if not raw.strip():
        raise GeminiError("Gemini 返回了空响应")

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Gemini returned non-JSON: %s", raw[:200])
        raise GeminiError(f"Gemini 返回的 JSON 无法解析：{exc}") from exc


def translate_sentence(sentence: str) -> dict:
    """Translate `sentence` and propose key words.

    Returns dict matching TranslationPayload schema:
      {"translation": "...", "key_words": [KeyWord, ...]}
    """
    data = _generate(
        system_prompt=_TRANSLATE_SYSTEM_PROMPT,
        user_text=sentence,
        schema_model=TranslationPayload,
    )
    # SDK already validated the JSON shape via response_schema, but trust-but-verify
    if "translation" not in data or "key_words" not in data:
        raise GeminiError("响应缺少必要字段")
    return data


def lookup_word(word: str, sentence: str, translation: str = "") -> dict:
    """Look up a single word in the context of a sentence.

    Returns dict matching KeyWord schema.
    """
    user_text = (
        f"原句：{sentence}\n"
        + (f"已知翻译：{translation}\n" if translation else "")
        + f"请解释单词：{word}"
    )
    data = _generate(
        system_prompt=_LOOKUP_SYSTEM_PROMPT,
        user_text=user_text,
        schema_model=KeyWord,
    )
    return data
