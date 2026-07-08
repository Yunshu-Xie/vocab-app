from __future__ import annotations

import json
import logging
from typing import Optional

from google import genai
from google.genai import types
from google.genai.errors import APIError

from app.config import settings
from app.models.schemas import KeyWord, TranslationPayload

logger = logging.getLogger(__name__)

# Gemini's raw errors (SDK internals, upstream JSON, tracebacks) are logged
# server-side but never sent to the client — only one of these fixed,
# actionable messages is. `retryable` tells the frontend whether offering a
# one-click retry makes sense (transient overload) or not (bad API key,
# request itself is the problem).
_RETRYABLE_STATUSES = {"UNAVAILABLE", "RESOURCE_EXHAUSTED", "DEADLINE_EXCEEDED", "INTERNAL"}
_AUTH_STATUSES = {"PERMISSION_DENIED", "UNAUTHENTICATED"}


def _classify_api_error(exc: APIError) -> tuple[str, bool]:
    status = exc.status or ""
    if status == "RESOURCE_EXHAUSTED":
        return "今日 API 调用额度已用完，请稍后再试或检查 Gemini 配额", False
    if status in _AUTH_STATUSES or exc.code in (401, 403):
        return "API Key 无效或权限不足，请检查 .env 中的 GEMINI_API_KEY", False
    if status in _RETRYABLE_STATUSES or exc.code in (503, 504):
        return "AI 服务当前繁忙，请稍后重试", True
    if exc.code == 400 or status == "INVALID_ARGUMENT":
        return "这句话 AI 处理不了，换一句试试", False
    return "AI 服务出错了，请稍后重试", True


_TRANSLATE_SYSTEM_PROMPT = """你是一个英语学习助手。给定一句英文，请：

1. 给出简洁、地道的中文翻译。
2. 从句中挑选 2-5 个有学习价值的词或固定词组放入 key_words：
   - 难度在 CEFR B1 及以上（即学术或较少见的词、短语动词、习语、固定搭配等）
   - 优先挑出真正的固定词组（如 give up、look forward to、in spite of 这类整体表意的搭配），
     而不是把普通形容词+名词拆开
   - 跳过 the / a / is / have / I / you 等极常见词
   - 每个词/词组都要按 schema 给出：
     - word（必须是原句中逐字出现的形式，若为词组则包含中间的单词和空格，不要改写措辞或时态）
     - lemma（词典原形；词组给规范形式，如 give up）
     - pos（词性英文：noun/verb/adjective/adverb 等；词组用 phrasal verb/idiom/collocation）
     - meaning_in_context（本句中的中文含义）
     - general_meaning（该词/词组常见的中文释义）
     - example（一句独立英文例句，不要复制原句）
     - difficulty（A1/A2/B1/B2/C1/C2 之一）

严格按照 response_schema 输出 JSON，不要附加解释。
"""

_LOOKUP_SYSTEM_PROMPT = """你是一个英语学习助手。
用户从下面这句英文里挑出一个单词或一个词组，请只为它输出一条词条：

- word：用户挑选的单词或词组（保留其在句中的形式）
- lemma：词典原形；词组给规范形式，如 give up
- pos：词性英文，如 noun/verb/adjective/adverb；词组用 phrasal verb/idiom/collocation
- meaning_in_context：该词/词组在本句中的中文含义（结合上下文，不要泛泛而谈）
- general_meaning：该词/词组常见的中文释义
- example：一句独立的英文例句，不可与原句相同
- difficulty：CEFR 难度等级 A1/A2/B1/B2/C1/C2 之一

严格按照 response_schema 输出 JSON，不要附加解释。
"""


_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise GeminiError(
                "还没有配置 API Key，请在 .env 中填入 GEMINI_API_KEY", retryable=False
            )
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


class GeminiError(RuntimeError):
    """A Gemini failure already translated into a message safe to show a user.

    `retryable` tells the caller whether a plain retry is worth offering —
    true for transient overload, false when retrying would just fail the
    same way (bad key, quota exhausted, malformed request).
    """

    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


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
    except APIError as exc:
        logger.exception("Gemini API call failed")
        message, retryable = _classify_api_error(exc)
        raise GeminiError(message, retryable=retryable) from exc
    except Exception as exc:
        logger.exception("Gemini API call failed")
        raise GeminiError("AI 服务暂时不可用，请稍后重试", retryable=True) from exc

    raw = response.text or ""
    if not raw.strip():
        raise GeminiError("AI 没有返回内容，请稍后重试", retryable=True)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Gemini returned non-JSON: %s", raw[:200])
        raise GeminiError("AI 返回的内容无法解析，请稍后重试", retryable=True) from exc


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
        raise GeminiError("AI 返回的内容不完整，请稍后重试", retryable=True)
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
