# Architecture

## Design Goals

1. Demonstrate the full engineering pipeline the task asks for: Sheets I/O,
   LLM orchestration with a review pass, state management, scheduling, config
   management, resilience.
2. Keep a human in the loop for any action that writes to LinkedIn
   (connection requests, status changes) rather than fully automating them.
3. Make every component independently testable without needing a live
   LinkedIn session (see `--mock` mode).

## Module Breakdown

### `services/sheets_service.py`
Thin wrapper around `gspread`. Two responsibilities only: read pending target
rows, write status/note/timestamp updates back. No business logic lives here,
so it can be swapped for a CSV-backed implementation in tests.

### `services/llm_service.py`
Implements the **two-pass note generation** the spec calls out as a specific
evaluation criterion:

1. **Draft pass** — given extracted profile context (name, headline, recent
   activity), generate a candidate note under the character limit.
2. **Review pass** — a second LLM call critiques the draft against a checklist
   (length, tone, genuineness, no hallucinated claims about the person, no
   over-familiarity) and either approves it or requests a rewrite. This loop
   runs up to 2 times before falling back to a safe generic template.

Provider-agnostic: works with NVIDIA NIM, OpenAI, Anthropic, or OpenRouter via
a single `LLM_PROVIDER` config switch, since they all expose an
OpenAI-compatible chat completions schema.

### `core/jitter.py`
Applies **stylistic** variation to approved notes: alternates greeting style
("Hi" / "Hello" / no greeting), optional emoji, sentence reordering, synonym
swaps for common phrases. This exists so that notes sent across many different
profiles don't read as copy-pasted templates to the *recipients* — a
legitimate goal for genuine personalization. It is explicitly not tuned
against LinkedIn's bot-detection systems (no timing jitter tied to detection
evasion, no fingerprint randomization) — see `KNOWN_LIMITATIONS.md`.

### `core/state_manager.py`
SQLite-backed local state (`outreach.db`) tracking every profile through
states: `pending -> drafted -> sent -> accepted/withdrawn/expired`. This is
the source of truth; Sheets is a synced view of it so the pipeline can resume
correctly even if it crashes mid-run.

### `core/scheduler.py`
Computes which `sent` rows have crossed the `FOLLOWUP_DAYS` threshold and
surfaces them for the human-confirmed follow-up check. Designed to be run via
cron / Task Scheduler / APScheduler — the script itself is stateless per
invocation.

### `browser/profile_extractor.py`
Playwright-based, read-only. Opens a profile URL in an already-authenticated
session (you log in manually once per run, same as the original error trace's
approach) and extracts: name, headline, current role line, and up to 3 recent
post snippets if visible — used only as LLM context, never auto-acted on.

## Data Flow

```
Google Sheet (targets)
        |
        v
[sheets_service.read_pending()]
        |
        v
[profile_extractor.extract(url)]  --> name, headline, recent_posts
        |
        v
[llm_service.draft_note(context)]  --> draft note
        |
        v
[llm_service.review_note(draft)]  --> approved note (or retry)
        |
        v
[jitter.vary(note)]  --> final note
        |
        v
   PRINT + CLIPBOARD + OPEN BROWSER TAB
        |
        v
   ( human clicks Connect -> Add note -> Send )
        |
        v
[state_manager.mark_sent()] + [sheets_service.write_status()]
        |
        v
   random delay (60-200s) --> next profile
```

## Why SQLite + Sheets, not just Sheets

Sheets API has rate limits and network latency unsuitable for being the
single source of truth during a run. SQLite gives instant local reads/writes
and crash recovery; Sheets is synced after each successful action so it stays
the human-readable, shareable view of progress.

## Config Precedence

`config/config.yaml` holds defaults; `.env` overrides them for
secrets/environment-specific values. This matches the spec's "config-driven,
no hardcoded values" requirement.
