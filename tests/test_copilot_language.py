"""Tests for copilot language instructions."""

from services.copilot_language import reply_language_instruction


def test_hinglish_question():
    instr = reply_language_instruction("linkedin nahi hai ??")
    assert "Hinglish" in instr
    assert "English only" in instr


def test_english_only_request():
    instr = reply_language_instruction("communicate in english only please")
    assert "English only" in instr


def test_hinglish_mode_request():
    instr = reply_language_instruction("use hindi and english mix")
    assert "Hinglish" in instr
