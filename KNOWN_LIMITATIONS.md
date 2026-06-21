# Known Limitations

## 1. Connection requests are human-confirmed, not auto-sent

**What the spec asked for:** Fully automated sending of up to 25 connection
requests per run, with "jitter" applied specifically to avoid LinkedIn's bot
detection.

**What this implementation does instead:** Drafts and reviews each note via
the two-pass LLM flow, then opens the profile in a visible, already-authenticated
browser session and pauses for a human to click Connect → Add a note → Send.

**Why:** LinkedIn's User Agreement prohibits automated sending of connection
requests via bots. Building detection-evasion behavior on top of that doesn't
change the underlying ToS violation, it just tries to hide it. Accounts running
this kind of automation are routinely flagged and suspended regardless of how
well-tuned the "human-like" jitter is, and at a company level this also carries
real legal exposure (LinkedIn has pursued litigation against firms building
exactly this kind of tooling). A human-in-the-loop design keeps the genuinely
useful parts (research, drafting, tracking) while removing the part that
violates platform terms.

**Engineering impact:** This is a deliberate scope decision, not a missing
feature. All the supporting infrastructure (Sheets sync, state management,
two-pass note generation, scheduler) is fully implemented as if it were feeding
an autonomous sender. Swapping the manual-confirm step for an automated click
is a small, isolated change in `main.py::send_connection_request()`, but one
the author chose not to make.

## 2. Acceptance detection is human-confirmed, not scraped

**What the spec asked for:** Automated checking of "Sent Invitations" or inbox
to detect acceptance status.

**What this implementation does instead:** The follow-up job opens the
"My Network -> Sent Invitations" page for the user and asks them to confirm
status per row (accepted / still pending / withdraw).

**Why:** LinkedIn doesn't expose a public API for invitation status, so any
automated detection requires scraping an authenticated page, which carries the
same ToS concerns as above, plus is brittle (LinkedIn changes its DOM/selectors
frequently, which the spec itself flags as a risk under "fallback selectors").
A 30-second manual confirmation per batch is more reliable than a scraper that
silently breaks.

## 3. Profile data extraction is best-effort

LinkedIn's DOM structure and class names change frequently and are obfuscated.
Extraction uses semantic selectors (aria-label, role attributes, text content)
where possible rather than brittle generated class names, but some fields
(recent activity, mutual connections) may not always be visible depending on
the target's privacy settings and your connection degree to them.

## 4. No multi-account or proxy rotation support

Out of scope per the original spec's boundaries (no cloud hosting,
multi-user support). This is designed for a single user running it against
their own authenticated session.

## 5. Rate limiting is conservative by design

Delays default to 60-200 seconds between profiles as specified, but because
sending itself is manual, actual throughput is also gated by how fast you
personally review and click. This is intentional.
