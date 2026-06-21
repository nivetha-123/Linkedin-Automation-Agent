# LinkedIn Outreach Assistant

A human-in-the-loop outreach pipeline: reads target profiles from Google Sheets,
extracts visible profile context, drafts a personalized connection note using a
two-pass LLM flow (draft → review), and tracks status in local state + Sheets.

## A Note on Scope (read this first)

The original task spec asked for fully autonomous, bulk LinkedIn connection-request
sending with "jitter" specifically designed to avoid LinkedIn's bot/automation
detection. That conflicts with LinkedIn's User Agreement (which prohibits automated
sending of connection requests), so this implementation deliberately does **not**
auto-click "Connect" / "Send" for you in bulk, and does not attempt to evade
detection systems.

What it *does* do, matching the spirit and most of the letter of the spec:

| Requirement | Status |
|---|---|
| Google Sheets read/write (targets, status, timestamps) | ✅ Implemented |
| Browser automation to extract profile context | ✅ Implemented (read-only) |
| Two-pass LLM note generation (draft + review) | ✅ Implemented |
| Note variation / phrasing jitter | ✅ Implemented (style variation, not anti-detection) |
| Local state management (SQLite) | ✅ Implemented |
| Scheduled follow-up job | ✅ Implemented (flags overdue requests for review) |
| Config-driven (.env / config.yaml) | ✅ Implemented |
| Auto-send connection requests in bulk | ❌ Not implemented (see below) |
| Anti-detection stealth behavior | ❌ Not implemented (see below) |

**Instead of auto-sending:** the tool opens each profile in a real, visible browser
window with the drafted note copied to your clipboard. You review the note and
click Connect → Add a note → paste → Send yourself, in your own pace, in your own
authenticated session. This keeps a human in the loop for every outbound action,
which is both safer for the account and arguably better practice for genuine
relationship-building outreach.

If acceptance auto-detection at scale is a hard requirement, see
`KNOWN_LIMITATIONS.md` for why that's also handled via a human-confirmed step
rather than automated inbox scraping.

## Project Structure

```
linkedin-outreach-assistant/
├── config/
│   └── config.yaml           # runtime configuration
├── services/
│   ├── sheets_service.py     # Google Sheets read/write (gspread)
│   └── llm_service.py        # two-pass note generation + review
├── core/
│   ├── state_manager.py      # SQLite local state tracking
│   ├── scheduler.py          # follow-up job (14-day check)
│   └── jitter.py             # human-like phrasing variation
├── browser/
│   └── profile_extractor.py  # read-only profile context extraction
├── main.py                   # orchestrates the full pipeline
├── requirements.txt
├── .env.example
├── linkedin_targets_template.csv
├── KNOWN_LIMITATIONS.md
└── ARCHITECTURE.md
```

## Setup

### 1. Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Google Sheets service account

1. Go to Google Cloud Console → create a project (or use existing)
2. Enable the **Google Sheets API** and **Google Drive API**
3. Create a Service Account → generate a JSON key
4. Save the key as `config/service_account.json` (gitignored)
5. Share your target Google Sheet with the service account's email
   (found inside the JSON as `client_email`)
6. Copy your Sheet ID from its URL into `.env`

### 3. Environment variables

```bash
cp .env.example .env
# then edit .env with your values
```

Required variables (see `.env.example` for full list):

```
GOOGLE_SHEET_ID=your_sheet_id_here
GOOGLE_SERVICE_ACCOUNT_PATH=config/service_account.json
LLM_PROVIDER=nvidia          # or openai / anthropic / openrouter
LLM_API_KEY=your_key_here
LLM_MODEL=meta/llama-3.1-70b-instruct
MAX_PROFILES_PER_RUN=25
MIN_DELAY_SECONDS=60
MAX_DELAY_SECONDS=200
FOLLOWUP_DAYS=14
```

### 4. Sheet template

Use `linkedin_targets_template.csv` as your starting Google Sheet. Required
columns: `profile_url, name_hint, status, note_used, sent_timestamp,
followup_due, final_status`.

## Running the outreach job

```bash
python main.py --mode outreach
```

This will:
1. Read up to `MAX_PROFILES_PER_RUN` pending rows from the Sheet
2. For each profile: open it in a visible browser, extract name/headline/recent
   activity, generate a draft note, run an LLM review pass, apply natural
   phrasing variation
3. Print the note and copy it to your clipboard, pause for you to review and
   send manually inside the open browser tab
4. After you confirm (press Enter), log status + timestamp back to the Sheet
   and local SQLite state
5. Wait a randomized delay (`MIN_DELAY_SECONDS`–`MAX_DELAY_SECONDS`) before the
   next profile — this paces *you*, not a bot, and is mainly there to avoid
   rapid-fire manual spam too

## Running the follow-up job

```bash
python main.py --mode followup
```

Checks local state for any `sent` requests older than `FOLLOWUP_DAYS`, opens
each one's "My Network → Sent Invitations" page for you to confirm
accepted/pending/expired, and updates the Sheet accordingly. See
`KNOWN_LIMITATIONS.md` for why this isn't fully automated.

## Testing with mock data

```bash
python main.py --mode outreach --mock
```

Runs the full pipeline against fixture data in `tests/fixtures/` without
opening a real browser or hitting Google Sheets — useful for verifying the
LLM note generation and state management logic in isolation.

## Known Limitations

See `KNOWN_LIMITATIONS.md`.

## Architecture

See `ARCHITECTURE.md` for design rationale.
