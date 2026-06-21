"""
Manages the human-confirmed connection request step.

Opens the profile in a visible browser tab (already authenticated), copies
the approved note to the clipboard, and pauses for the human to review and
click Connect -> Add a note -> Send themselves. This is the deliberate design
boundary explained in KNOWN_LIMITATIONS.md -- the tool never auto-clicks
Connect or Send.
"""
import pyperclip
from loguru import logger
from playwright.sync_api import Page


def present_for_manual_send(page: Page, profile_url: str, note: str) -> bool:
    """Bring the profile into view, copy the note to clipboard, and wait for
    the human to confirm they've sent it (or chosen to skip).

    Returns True if the user confirms they sent it, False if skipped.
    """
    page.goto(profile_url, wait_until="domcontentloaded")
    page.bring_to_front()

    pyperclip.copy(note)

    print("\n" + "=" * 70)
    print(f"Profile open in browser: {profile_url}")
    print(f"Drafted note ({len(note)} chars, copied to clipboard):")
    print(f"  \"{note}\"")
    print("=" * 70)
    print("Review the profile, click Connect -> Add a note -> paste -> Send.")

    choice = input("Press Enter once sent, or type 's' to skip this profile: ").strip().lower()
    if choice == "s":
        logger.info(f"Skipped: {profile_url}")
        return False

    logger.info(f"Confirmed sent by user: {profile_url}")
    return True
