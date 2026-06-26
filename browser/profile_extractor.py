"""
Read-only profile context extraction. Opens a profile URL in an
already-authenticated session (you log in manually once per run) and
extracts visible context to feed the LLM. Never auto-clicks Connect/Send --
see browser/outreach_session.py for the human-confirmed send step.

Uses semantic selectors (aria-label, role, text content) in preference to
generated class names, which LinkedIn rotates frequently and which the task
spec itself flags as a fragility risk.

NOTE: LinkedIn's DOM changes periodically. If extraction quality degrades,
call debug_dump_dom() once against a live profile and re-derive selectors
from the saved HTML rather than guessing blind.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger
from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeout


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


def _safe_text(scope: Page | Locator, selector: str, timeout: int = 3000) -> str:
    """Works against either a Page or a Locator scope -- both expose
    .locator(), so this stays usable for top-card-scoped lookups."""
    try:
        el = scope.locator(selector).first
        el.wait_for(state="visible", timeout=timeout)
        text = el.text_content()
        return text.strip() if text else ""
    except PlaywrightTimeout:
        return ""
    except Exception as e:
        logger.debug(f"Selector '{selector}' failed: {e}")
        return ""


def debug_dump_dom(page: Page, path: str = "debug_profile.html") -> None:
    """One-time diagnostic: dump the fully-rendered DOM so you can search
    for real headline/post text and find their current container
    selectors, instead of guessing against stale ones."""
    try:
        Path(path).write_text(page.content())
        logger.info(f"Dumped DOM to {path}")
    except Exception as e:
        logger.warning(f"Could not dump DOM: {e}")


def _extract_name(page: Page) -> str:
    name = _safe_text(page, "h1")
    if name:
        return name
    title = page.title().split("|")[0].strip()
    return title or "Unknown"


def _extract_headline(page: Page) -> str:
    # Scope to the profile top card first -- "div.text-body-medium" alone
    # matches many unrelated elements across the page (it's a reused
    # utility class), so searching the whole page risks grabbing the
    # wrong text entirely, not just a stale selector.
    top_card = page.locator("main section.artdeco-card").first
    try:
        top_card.wait_for(state="attached", timeout=5000)
    except PlaywrightTimeout:
        logger.warning("Top card container not found; falling back to page-wide search")
        return _safe_text(page, "div.text-body-medium") or _safe_text(
            page, "[data-generated-suggestion-target]"
        )

    headline = _safe_text(top_card, "div.text-body-medium")
    if not headline:
        headline = _safe_text(page, "[data-generated-suggestion-target]")
    return headline


def _extract_current_role(page: Page) -> str:
    # id="experience" is frequently on an anchor near the section rather
    # than the section itself, and aria-hidden spans are duplicated
    # (visible + accessible pairs) inside each entry. Scope narrowly to
    # the first list item to reduce the chance of grabbing the wrong span.
    exp_section = page.locator(
        "section:has(a#experience), section:has(div#experience)"
    ).first
    try:
        exp_section.wait_for(state="attached", timeout=5000)
    except PlaywrightTimeout:
        logger.debug("Experience section not found for this profile")
        return ""

    first_entry = exp_section.locator("li").first
    return _safe_text(first_entry, "span[aria-hidden='true']")


def _extract_recent_posts(page: Page, max_posts: int = 3) -> list[str]:
    # The activity module is frequently lazy-loaded and may not be present
    # on the main profile page at all -- scroll first to give it a chance
    # to mount before counting, and try multiple known class names since
    # this is one of the more volatile parts of the DOM.
    posts: list[str] = []
    try:
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(1500)

        candidates = [
            "div.update-components-text",
            "div.feed-shared-update-v2__description",
        ]
        post_locator = None
        for sel in candidates:
            loc = page.locator(sel)
            if loc.count() > 0:
                post_locator = loc
                break

        if post_locator is None:
            logger.debug("No recent-activity posts found with known selectors")
            return posts

        count = min(post_locator.count(), max_posts)
        for i in range(count):
            text = post_locator.nth(i).text_content()
            if text and text.strip():
                posts.append(text.strip())
    except Exception as e:
        logger.debug(f"Could not extract recent posts: {e}")
    return posts


def extract_profile(page: Page, profile_url: str) -> ProfileContext:
    """Navigate to a profile and extract visible context. Read-only --
    does not click, like, comment, or send anything."""
    page.goto(profile_url, wait_until="domcontentloaded")

    try:
        page.locator("h1").first.wait_for(state="visible", timeout=8000)
    except PlaywrightTimeout:
        logger.warning(f"Profile header never appeared for {profile_url}")

    name = _extract_name(page)
    headline = _extract_headline(page) or "Unknown"
    current_role = _extract_current_role(page)
    recent_posts = _extract_recent_posts(page)

    ctx = ProfileContext(
        url=profile_url,
        name=name,
        headline=headline,
        current_role=current_role,
        recent_posts=recent_posts,
    )

    if name == "Unknown" or headline == "Unknown" or not recent_posts:
        logger.warning(
            f"Partial extraction for {profile_url} -- "
            f"name_ok={name != 'Unknown'} headline_ok={headline != 'Unknown'} "
            f"posts_found={len(recent_posts)}. Consider debug_dump_dom() to "
            f"re-check selectors against current LinkedIn markup."
        )

    logger.info(f"Extracted profile: {ctx.name} | {ctx.headline}")
    return ctx
