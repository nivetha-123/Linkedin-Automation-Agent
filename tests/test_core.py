"""
Basic unit tests for components that don't require network/browser access.
Run with: python -m pytest tests/
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.jitter import vary_greeting, maybe_add_emoji, vary
from services.llm_service import LLMService


def test_vary_greeting_replaces_opener():
    note = "Hi Jane, I saw your post about computer vision and wanted to connect."
    result = vary_greeting(note, "Jane")
    assert "Jane" in result
    assert len(result) > 0


def test_vary_greeting_leaves_non_greeting_notes_alone():
    note = "Loved your recent talk on NLP — would be great to connect."
    result = vary_greeting(note, "Jane")
    assert result == note


def test_maybe_add_emoji_respects_probability_zero():
    note = "Hi Jane, great to see your work."
    result = maybe_add_emoji(note, probability=0.0)
    assert result == note


def test_vary_full_pipeline_keeps_text_intact():
    note = "Hi Jane, I'd love to connect and learn more about your CV work."
    result = vary(note, name="Jane")
    assert "Jane" in result
    assert "connect" in result.lower()


def test_parse_review_approve():
    raw = "VERDICT: APPROVE\nISSUES: none\nREVISED_NOTE:"
    parsed = LLMService._parse_review(raw, fallback_draft="original draft")
    assert parsed["approved"] is True
    assert parsed["issues"] == []


def test_parse_review_rewrite():
    raw = "VERDICT: REWRITE\nISSUES: too generic, too long\nREVISED_NOTE: Hi Jane, loved your OCR work."
    parsed = LLMService._parse_review(raw, fallback_draft="original draft")
    assert parsed["approved"] is False
    assert "too generic" in parsed["issues"]
    assert "Hi Jane" in parsed["revised_note"]


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
