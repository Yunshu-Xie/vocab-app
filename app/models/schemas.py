from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class TranslateRequest(BaseModel):
    sentence: str = Field(..., min_length=1, max_length=1000)


class LookupRequest(BaseModel):
    word: str = Field(..., min_length=1, max_length=120)
    sentence: str = Field(..., min_length=1, max_length=1000)
    translation: str = Field("", max_length=1000)


class Token(BaseModel):
    text: str
    is_word: bool
    lower: Optional[str] = None


class KeyWord(BaseModel):
    word: str = Field(
        ..., description="The word or fixed phrase exactly as it appears in the sentence"
    )
    lemma: str = Field(
        ...,
        description="Dictionary base form, e.g. 'run' for 'running'; "
        "for a phrase, its canonical form, e.g. 'give up'",
    )
    pos: str = Field(
        ...,
        description="Part of speech, e.g. 'noun', 'verb', 'adjective'; "
        "for multi-word expressions use 'phrasal verb', 'idiom', or 'collocation'",
    )
    meaning_in_context: str = Field(..., description="本句中该词/词组的中文含义")
    general_meaning: str = Field(..., description="该词/词组常见的中文释义")
    example: str = Field(..., description="一句独立的英文例句（不同于原句）")
    difficulty: str = Field(..., description="CEFR 难度等级：A1/A2/B1/B2/C1/C2")


class TranslationPayload(BaseModel):
    """Schema enforced on the Gemini response for /api/translate."""

    translation: str = Field(..., description="原句的简洁中文翻译")
    key_words: list[KeyWord] = Field(
        ...,
        description="从句中挑选的 2-5 个 B1 及以上难度、有学习价值的词或固定词组；"
        "跳过 the/is/have 等常见词",
    )


class TranslatedKeyWord(KeyWord):
    """A KeyWord located back in the original sentence's token list."""

    start_idx: Optional[int] = Field(
        None, description="Index of the first token (inclusive) this word/phrase spans"
    )
    end_idx: Optional[int] = Field(
        None, description="Index of the last token (inclusive) this word/phrase spans"
    )


class TranslateResponse(BaseModel):
    translation: str
    tokens: list[Token]
    key_words: list[TranslatedKeyWord]


class VocabCreate(BaseModel):
    word: str = Field(..., min_length=1, max_length=120)
    lemma: str = Field("", max_length=120)
    pos: str = Field("", max_length=32)
    meaning: str = Field(..., min_length=1, max_length=500)
    example: str = Field("", max_length=500)
    source_sentence: str = Field("", max_length=1000)
    source_translation: str = Field("", max_length=1000)
    notes: str = Field("", max_length=500)


class VocabUpdate(BaseModel):
    meaning: Optional[str] = Field(None, max_length=500)
    example: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = Field(None, max_length=500)


class VocabResponse(BaseModel):
    id: int
    word: str
    lemma: str
    pos: str
    meaning: str
    example: str
    source_sentence: str
    source_translation: str
    notes: str
    created_at: str


class VocabListResponse(BaseModel):
    items: list[VocabResponse]
    total: int
    page: int
    limit: int
