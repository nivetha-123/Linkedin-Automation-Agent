"""
Read-only profile context extraction. Opens a profile URL in an
already-authenticated session (you log in manually once per run) and
extracts visible context to feed the LLM. Never auto-clicks Connect/Send --
see browser/outreach_session.py for the human-confirmed send step.

Uses semantic selectors (aria-label, role, text content) in preference to
generated class names, which LinkedIn rotates frequently and which the task
spec itself flags as a fragility risk.
"""
from dataclasses import dataclass, field

from loguru import logger
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout


@dataclass
class ProfileContext:
    url: str
    name: str = "Unknown"
    headline: str = "Unknown"
    current_role: str = ""
    recent_posts: list[str] = field(default_factory=list)

    def to_prompt_context(self) -> str:
        lines = [f"Name: {self.name}", f"Headline: {self.headline}"]
        if self.current_role:
            lines.append(f"Current role: {self.current_role}")
        if self.recent_posts:
            lines.append("Recent activity:")
            for p in self.recent_posts:
                lines.append(f"  - {p[:200]}")
        return "\n".join(lines)


def _safe_text(page: Page, selector: str, timeout: int = 3000) -> str:
    try:
        el = page.locator(selector).first
        el.wait_for(state="visible", timeout=timeout)
        return el.text_content().strip()
    except PlaywrightTimeout:
        return ""
    except Exception as e:
        logger.debug(f"Selector '{selector}' failed: {e}")
        return ""


def extract_profile(page: Page, profile_url: str) -> ProfileContext:
    """Navigate to a profile and extract visible context. Read-only --
    does not click, like, comment, or send anything."""
    page.goto(profile_url, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    name = (
        _safe_text(page, "h1")
        or page.title().split("|")[0].strip()
        or "Unknown"
    )

    headline = _safe_text(page, "div.text-body-medium") or _safe_text(
        page, "[data-generated-suggestion-target]"
    )

    current_role = _safe_text(page, "section#experience li span[aria-hidden='true']")

    recent_posts = []
    try:
        post_locator = page.locator("div.feed-shared-update-v2__description")
        count = min(post_locator.count(), 3)
        for i in range(count):
            text = post_locator.nth(i).text_content()
            if text and text.strip():
                recent_posts.append(text.strip())
    except Exception as e:
        logger.debug(f"Could not extract recent posts: {e}")

    ctx = ProfileContext(
        url=profile_url,
        name=name,
        headline=headline or "Unknown",
        current_role=current_role,
        recent_posts=recent_posts,
    )
    logger.info(f"Extracted profile: {ctx.name} | {ctx.headline}")
    return ctx
