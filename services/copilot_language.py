"""Language instructions for LLM replies — no static answers, prompt shaping only."""

from __future__ import annotations

import re


def reply_language_instruction(message: str) -> str:
    """Tell the model which language to use based on the analyst message."""
    lower = message.lower()

    if re.search(
        r"\b(english only|only english|reply in english|communicate in english|speak english|talk in english)\b",
        lower,
    ):
        return "LANGUAGE: Reply in English only."

    if re.search(
        r"\b(hinglish|hindi and english|hindi \+ english|hindi english|mix hindi english)\b",
        lower,
    ):
        return "LANGUAGE: Reply in Hinglish — natural Hindi + English mix, same style as the analyst."

    if re.search(r"\b(hindi only|reply in hindi|hindi mein|हिंदी|देवनागरी)\b", lower):
        return "LANGUAGE: Reply in Hindi (Devanagari or Roman). Do not use English-only sentences."

    if any("\u0900" <= ch <= "\u097f" for ch in message):
        return (
            "LANGUAGE: The analyst wrote in Hindi. Reply in Hindi or Hinglish — "
            "do NOT reply in English only."
        )

    if re.search(
        r"\b(hai|hain|nahi|nahin|kya|kaise|kab|kyun|iska|uska|linkedin nahi|dikhao|batao|karo)\b",
        lower,
    ):
        return (
            "LANGUAGE: The analyst wrote in Hinglish. Reply in Hinglish (Hindi + English mix) — "
            "do NOT reply in English only."
        )

    return "LANGUAGE: Match the analyst's language (English, Hindi, or Hinglish)."
