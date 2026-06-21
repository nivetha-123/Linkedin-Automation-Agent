"""
Applies stylistic variation to approved notes so that outreach across many
different recipients doesn't read as copy-pasted to *them*.

This is explicitly scoped to natural-language variation for genuine
personalization -- NOT timing/behavioral jitter aimed at evading platform
detection systems. See KNOWN_LIMITATIONS.md for that distinction.
"""
import random

GREETINGS = ["Hi {name},", "Hello {name},", "{name},", "Hi {name} —"]
SIGN_OFFS = ["Best,", "Thanks,", "Cheers,", ""]
EMOJI_POOL = ["", "", "", "🙂", "👋"]  # mostly empty -- emoji should be rare, not default


def vary_greeting(note: str, name: str) -> str:
    """Replace a generic 'Hi {name}' opener with a randomly chosen style,
    if the note starts with a name-based greeting."""
    if not note.lower().startswith(("hi", "hello", name.lower())):
        return note

    chosen = random.choice(GREETINGS).format(name=name)
    # find where the original greeting ends (first comma or dash)
    for sep in [",", "—", "-"]:
        if sep in note[:40]:
            rest = note.split(sep, 1)[1].strip()
            return f"{chosen} {rest}"
    return note


def maybe_add_emoji(note: str, probability: float = 0.15) -> str:
    """Rarely append a soft emoji -- most notes should have none, to avoid
    looking templated in the opposite direction (over-decorated)."""
    if random.random() < probability:
        emoji = random.choice([e for e in EMOJI_POOL if e])
        if emoji and not note.rstrip().endswith(emoji):
            return f"{note.rstrip()} {emoji}"
    return note


def vary(note: str, name: str = "there") -> str:
    """Apply the full jitter pipeline to a single approved note."""
    out = vary_greeting(note, name)
    out = maybe_add_emoji(out)
    return out.strip()
