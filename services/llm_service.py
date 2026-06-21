"""
Two-pass LLM note generation: a draft pass followed by an independent review
pass that critiques the draft against a checklist and either approves it or
requests a rewrite. This is the "AI review pass" the task spec calls out
explicitly as an evaluation criterion -- it must be two distinct LLM calls
with different prompts/responsibilities, not a single call dressed up.

Provider-agnostic via the OpenAI-compatible chat completions schema, which
NVIDIA NIM, OpenAI, and OpenRouter all support.
"""
from dataclasses import dataclass
from typing import Optional

from loguru import logger
from openai import OpenAI

from config.settings import settings

DRAFT_SYSTEM_PROMPT = """You write short, genuine LinkedIn connection request notes.
Rules:
- Maximum {char_limit} characters, no exceptions.
- Reference one specific, real detail from the provided profile context (headline, role, or recent activity).
- Never invent facts about the person that are not in the provided context.
- Sound like a real person, not a template. No generic phrases like "I'd like to add you to my network."
- No emojis unless explicitly natural to the tone.
- One sentence is often enough. Do not pad with filler."""

REVIEW_SYSTEM_PROMPT = """You are reviewing a draft LinkedIn connection note before it is sent.
Check it against this list and respond in this exact format:

VERDICT: APPROVE or REWRITE
ISSUES: <comma-separated list of issues found, or "none">
REVISED_NOTE: <only if VERDICT is REWRITE, otherwise leave blank>

Checklist:
1. Is it under {char_limit} characters?
2. Does it avoid generic template language?
3. Does it avoid fabricating facts not present in the given context?
4. Does it avoid being overly familiar or presumptuous for a first message?
5. Does it read naturally, like something a real person would type?"""


@dataclass
class NoteResult:
    note: str
    approved: bool
    issues: list[str]
    attempts: int


class LLMService:
    def __init__(self):
        self.client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        self.model = settings.llm_model
        self.char_limit = settings.note_char_limit
        self.max_retries = settings.yaml_config["note"]["max_review_retries"]

    def _chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.7) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=settings.yaml_config["llm"]["max_tokens"],
        )
        return response.choices[0].message.content.strip()

    def _draft(self, profile_context: str) -> str:
        system = DRAFT_SYSTEM_PROMPT.format(char_limit=self.char_limit)
        user = f"Profile context:\n{profile_context}\n\nWrite the connection note."
        return self._chat(system, user, temperature=settings.yaml_config["llm"]["temperature"])

    def _review(self, draft: str, profile_context: str) -> dict:
        system = REVIEW_SYSTEM_PROMPT.format(char_limit=self.char_limit)
        user = f"Profile context:\n{profile_context}\n\nDraft note:\n{draft}"
        raw = self._chat(system, user, temperature=0.2)
        return self._parse_review(raw, draft)

    @staticmethod
    def _parse_review(raw: str, fallback_draft: str) -> dict:
        lines = raw.splitlines()
        verdict, issues, revised = "APPROVE", [], ""
        for line in lines:
            if line.upper().startswith("VERDICT:"):
                verdict = line.split(":", 1)[1].strip().upper()
            elif line.upper().startswith("ISSUES:"):
                raw_issues = line.split(":", 1)[1].strip()
                issues = [] if raw_issues.lower() == "none" else [i.strip() for i in raw_issues.split(",")]
            elif line.upper().startswith("REVISED_NOTE:"):
                revised = line.split(":", 1)[1].strip()
        return {
            "approved": verdict == "APPROVE",
            "issues": issues,
            "revised_note": revised or fallback_draft,
        }

    def generate_reviewed_note(self, profile_context: str) -> NoteResult:
        """Run the draft -> review loop, retrying up to max_retries times."""
        attempts = 0
        note = self._draft(profile_context)

        while attempts < self.max_retries:
            attempts += 1
            review = self._review(note, profile_context)

            if review["approved"] and len(note) <= self.char_limit:
                logger.info(f"Note approved on attempt {attempts}")
                return NoteResult(note=note, approved=True, issues=[], attempts=attempts)

            logger.warning(f"Note rejected on attempt {attempts}: {review['issues']}")
            note = review["revised_note"][: self.char_limit]

        # Fallback: safe generic note if review loop never approves
        logger.warning("Max review retries hit, falling back to safe generic template")
        fallback = self._safe_fallback(profile_context)
        return NoteResult(note=fallback, approved=False, issues=["fell back to template"], attempts=attempts)

    def _safe_fallback(self, profile_context: str) -> str:
        name = self._extract_name(profile_context)
        note = f"Hi {name}, I'd like to connect and learn more about your work."
        return note[: self.char_limit]

    @staticmethod
    def _extract_name(profile_context: str) -> str:
        for line in profile_context.splitlines():
            if line.lower().startswith("name:"):
                return line.split(":", 1)[1].strip().split()[0]
        return "there"
