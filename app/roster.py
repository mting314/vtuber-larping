"""Canonical VTuber roster — the single source of truth for tracked channels.

Kept out of app.main so operational scripts (scratch/) can import it without
pulling in the FastAPI app.

Order is cosmetic: it determines the autoincrement ids a *freshly seeded* DB
hands out, and is arranged to match the historical order in the GCS database so
the two line up. Nothing may depend on that alignment — ids are per-database and
`app.persistence` deliberately resolves channels by `channel_id` instead. See
docs/design.md §6.

Historical note: earlier databases were seeded with malformed channel_ids (14
characters, e.g. "UC_RxY1ovTm5bY", against the real 24). Those are repaired at
startup and by scratch/fix_vtuber_channel_ids.py.
"""

# (name, channel_id, agency) — channel_ids verified against YouTube 2026-08-16.
ROSTER: list[tuple[str, str, str]] = [
    ("Shiori Novella", "UCgnfPPb9JI3e9A4cXHnWbyg", "Hololive English"),
    ("Kobo Kanaeru", "UCjLEmnpCNeisMxy134KPwWw", "Hololive ID"),
    ("Nerissa Ravencroft", "UC_sFNM0z0MWm9A6WlKPuMMg", "Hololive English"),
    ("Vestia Zeta", "UCTvHWSfBZgtxE4sILOaurIQ", "Hololive ID"),
    ("Ironmouse", "UCj_TYZ60NDQYY5QpUvOge9g", "VShojo"),
    ("Gawr Gura", "UCoSrY_IQQVpmIRZ9Xf-y93g", "Hololive English"),
    ("Hakos Baelz", "UCgmPnx-EEeOrZSg5Tiw7ZRQ", "Hololive English"),
    ("FUWAMOCO", "UCt9H_RpQzhxzlyBxFqrdHqA", "Hololive English"),
    ("Ninomae Ina'nis", "UCMwGHR0BTZuLsmjY_NT5Pwg", "Hololive English"),
    ("IRyS", "UC8rcEBzJSleTkf_-agPM20g", "Hololive English"),
]

# Alternate spellings that exist in older databases, mapped to the ROSTER name.
NAME_ALIASES: dict[str, str] = {
    "Zeta Vestia": "Vestia Zeta",
}

CANONICAL_CHANNEL_IDS: dict[str, str] = {name: channel_id for name, channel_id, _ in ROSTER}
AGENCIES: dict[str, str] = {name: agency for name, _, agency in ROSTER}


def canonical_name(name: str) -> str:
    """Resolve a possibly-legacy display name to its ROSTER spelling."""
    return NAME_ALIASES.get(name, name)


def canonical_channel_id(name: str) -> str | None:
    """Canonical channel_id for a VTuber name, tolerating legacy spellings."""
    return CANONICAL_CHANNEL_IDS.get(canonical_name(name))
