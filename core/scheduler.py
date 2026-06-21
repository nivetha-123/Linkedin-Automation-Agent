"""
Computes which 'sent' rows have crossed the FOLLOWUP_DAYS threshold and
surfaces them for a human-confirmed check (see KNOWN_LIMITATIONS.md for why
acceptance detection is not auto-scraped).

Run standalone via `python main.py --mode followup`, or schedule with cron:
    0 9 * * *  cd /path/to/project && .venv/bin/python main.py --mode followup
or with APScheduler if you prefer a long-running process -- see
run_with_apscheduler() below for that variant.
"""
from loguru import logger

from core.state_manager import StateManager
from services.sheets_service import SheetsService


def run_followup_check(state: StateManager, sheets: SheetsService):
    overdue = state.get_overdue_followups()
    if not overdue:
        logger.info("No follow-ups due today.")
        return

    logger.info(f"{len(overdue)} connection requests are due for follow-up review.")
    for row in overdue:
        print(f"\nProfile: {row['profile_url']}")
        print(f"  Name: {row['name']}")
        print(f"  Sent: {row['sent_timestamp']}")
        print(f"  Note used: {row['note_used']}")
        print("  Open 'My Network > Sent Invitations' in your browser to check status.")

        choice = input("  Status? [a]ccepted / [p]ending (skip) / [w]ithdraw: ").strip().lower()
        if choice == "a":
            state.mark_final(row["profile_url"], "accepted")
            if row["sheet_row_index"]:
                sheets.mark_final_status(row["sheet_row_index"], "accepted")
        elif choice == "w":
            state.mark_final(row["profile_url"], "withdrawn")
            if row["sheet_row_index"]:
                sheets.mark_final_status(row["sheet_row_index"], "withdrawn")
            print("  -> Manually withdraw this invitation in LinkedIn's Sent Invitations page.")
        else:
            logger.info(f"Skipped {row['profile_url']} (still pending)")


def run_with_apscheduler():
    """Optional: run as a long-lived process that checks daily instead of
    relying on external cron. Most users should just use cron/Task Scheduler
    and `python main.py --mode followup` -- this is here for completeness
    per the spec's APScheduler suggestion."""
    from apscheduler.schedulers.blocking import BlockingScheduler

    state = StateManager()
    sheets = SheetsService()
    scheduler = BlockingScheduler()
    scheduler.add_job(lambda: run_followup_check(state, sheets), "interval", days=1)
    logger.info("Scheduler started -- checking follow-ups once per day.")
    scheduler.start()
