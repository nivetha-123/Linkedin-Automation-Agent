"""
Orchestrates the full outreach pipeline.

Usage:
    python main.py --mode outreach          # run the outreach job
    python main.py --mode outreach --mock   # run against local fixtures, no browser/sheets
    python main.py --mode followup          # run the follow-up check job
"""
import argparse
import random
import sys
import time
from pathlib import Path

from loguru import logger
from playwright.sync_api import sync_playwright

from browser.outreach_session import present_for_manual_send
from browser.profile_extractor import extract_profile
from config.settings import settings
from core.jitter import vary
from core.scheduler import run_followup_check
from core.state_manager import StateManager
from services.llm_service import LLMService
from services.sheets_service import SheetsService

logger.remove()
logger.add(sys.stderr, level=settings.log_level)
logger.add(settings.log_path, rotation=f"{settings.yaml_config['logging']['rotate_mb']} MB",
           retention=f"{settings.yaml_config['logging']['retain_days']} days", level="DEBUG")


def run_outreach(mock: bool = False):
    state = StateManager()
    llm = LLMService()

    if mock:
        _run_outreach_mock(state, llm)
        return

    sheets = SheetsService()
    targets = sheets.read_pending(limit=settings.max_profiles_per_run)
    print(targets,'targetsmains')
    if not targets:
        logger.info("No pending targets found in sheet.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=settings.yaml_config["browser"]["headless"],
            slow_mo=settings.yaml_config["browser"]["slow_mo_ms"],
        )
        context = browser.new_context(
            viewport=settings.yaml_config["browser"]["viewport"]
        )
        page = context.new_page()

        page.goto("https://www.linkedin.com/login")
        input("Log in manually, then press Enter once you see your feed/home: ")
        page.wait_for_timeout(2000)

        for i, target in enumerate(targets):
            url = target["profile_url"]
            row_index = target["_row_index"]
            logger.info(f"[{i+1}/{len(targets)}] Processing {url}")

            try:
                ctx = extract_profile(page, url)
                state.upsert_pending(url, row_index, ctx.name, ctx.headline)

                result = llm.generate_reviewed_note(ctx.to_prompt_context())
                final_note = vary(result.note, name=ctx.name.split()[0] if ctx.name else "there")

                sent = present_for_manual_send(page, url, final_note)
                if sent:
                    state.mark_sent(url, final_note)
                    sheets.mark_sent(row_index, final_note)
                else:
                    sheets.update_row(row_index, {"status": "skipped"})

            except Exception as e:
                logger.exception(f"Failed processing {url}: {e}")
                _capture_failure_screenshot(page, url)
                sheets.update_row(row_index, {"status": "error"})
                continue

            if i < len(targets) - 1:
                delay = random.uniform(settings.min_delay_seconds, settings.max_delay_seconds)
                logger.info(f"Pausing {delay:.0f}s before next profile...")
                time.sleep(delay)

        browser.close()

    logger.info("Outreach run complete.")


def _capture_failure_screenshot(page, url: str):
    try:
        Path(settings.screenshot_dir).mkdir(parents=True, exist_ok=True)
        safe_name = url.rstrip("/").split("/")[-1] or "profile"
        path = f"{settings.screenshot_dir}/{safe_name}.png"
        page.screenshot(path=path)
        logger.info(f"Saved failure screenshot to {path}")
    except Exception as e:
        logger.warning(f"Could not capture screenshot: {e}")


def _run_outreach_mock(state: StateManager, llm: LLMService):
    """Run the note-generation + state-tracking logic against fixture data,
    without touching a real browser or Google Sheets. Useful for verifying
    the LLM pipeline and state management in isolation."""
    import json

    fixture_path = Path(__file__).parent / "tests" / "fixtures" / "mock_profiles.json"
    with open(fixture_path) as f:
        profiles = json.load(f)

    for i, p in enumerate(profiles):
        logger.info(f"[MOCK {i+1}/{len(profiles)}] {p['url']}")
        context_str = f"Name: {p['name']}\nHeadline: {p['headline']}"
        result = llm.generate_reviewed_note(context_str)
        final_note = vary(result.note, name=p["name"].split()[0])

        print(f"\nProfile: {p['url']}")
        print(f"Generated note ({len(final_note)} chars): \"{final_note}\"")
        print(f"Approved on attempt: {result.attempts}")

        state.upsert_pending(p["url"], sheet_row_index=0, name=p["name"], headline=p["headline"])
        state.mark_sent(p["url"], final_note)

    logger.info("Mock run complete. Check core/outreach.db for state.")


def run_followup():
    state = StateManager()
    sheets = SheetsService()
    run_followup_check(state, sheets)


def main():
    parser = argparse.ArgumentParser(description="LinkedIn Outreach Assistant")
    parser.add_argument("--mode", choices=["outreach", "followup"], required=True)
    parser.add_argument("--mock", action="store_true", help="Run outreach against local fixtures, no browser/sheets")
    args = parser.parse_args()

    if args.mode == "outreach":
        run_outreach(mock=args.mock)
    elif args.mode == "followup":
        run_followup()


if __name__ == "__main__":
    main()
