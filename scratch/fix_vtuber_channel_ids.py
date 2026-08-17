"""Repair malformed VTuber channel_ids in the shared GCS database.

Older databases were seeded with fabricated channel_ids (mostly 14 characters,
e.g. "UC_RxY1ovTm5bY", against YouTube's real 24). app.main repairs these at
startup, but only inside the container — the GCS copy keeps the bad value. That
divergence makes app.persistence._apply_to look up a channel_id the remote has
never seen, which (before the name fallback existed) forked each VTuber into two
rows and split their streams.

This fixes the data at the source so local and remote agree.

Also merges duplicate VTuber rows: if two rows resolve to the same canonical
channel, streams are re-pointed at the survivor and the duplicate is deleted.
That makes the script idempotent and usable as a repair tool if forks ever occur.

Usage:
    python -m scratch.fix_vtuber_channel_ids            # dry run, prints a plan
    python -m scratch.fix_vtuber_channel_ids --apply    # pull, fix, push to GCS

Dry run touches nothing: it pulls the DB to a temp file and reports. Only
--apply writes back to GCS.
"""

import argparse
import os
import shutil
import sys
import tempfile

from sqlmodel import Session, create_engine, select

from app.database import init_db
from app.models import Stream, VTuber
from app.roster import canonical_channel_id, canonical_name
from app.storage import storage_manager

sys.stdout.reconfigure(encoding="utf-8")


def plan_and_apply(session: Session, apply: bool) -> int:
    """Report (and optionally perform) channel_id repairs and duplicate merges."""
    vtubers = session.exec(select(VTuber)).all()
    changes = 0

    # Group by canonical name so duplicates land together.
    by_name: dict[str, list[VTuber]] = {}
    for v in vtubers:
        by_name.setdefault(canonical_name(v.name), []).append(v)

    print(f"{'vtuber':<22}{'current channel_id':<28}{'action'}")
    print("-" * 88)

    for name, rows in sorted(by_name.items()):
        correct = canonical_channel_id(name)

        if correct is None:
            for v in rows:
                print(f"{v.name:<22}{v.channel_id:<28}SKIP — not in ROSTER, no canonical id known")
            continue

        # Survivor: prefer a row that already has the right id, else the lowest
        # id so existing stream FKs mostly stay valid.
        rows.sort(key=lambda v: (v.channel_id != correct, v.id))
        survivor, dupes = rows[0], rows[1:]

        if survivor.channel_id != correct:
            print(f"{survivor.name:<22}{survivor.channel_id:<28}FIX  -> {correct}")
            if apply:
                survivor.channel_id = correct
                session.add(survivor)
            changes += 1
        else:
            print(f"{survivor.name:<22}{survivor.channel_id:<28}ok")

        for dupe in dupes:
            moved = session.exec(select(Stream).where(Stream.vtuber_id == dupe.id)).all()
            print(
                f"{dupe.name:<22}{dupe.channel_id:<28}"
                f"MERGE into id={survivor.id} ({len(moved)} stream(s) re-pointed), then delete"
            )
            if apply:
                for st in moved:
                    st.vtuber_id = survivor.id
                    session.add(st)
                session.delete(dupe)
            changes += 1

    if apply:
        session.commit()
    return changes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the repaired DB back to GCS")
    args = parser.parse_args()

    work_dir = tempfile.mkdtemp(prefix="vtuber-roster-fix-")
    db_path = os.path.join(work_dir, "vtuber_digest.db")
    try:
        generation = storage_manager.download_db_with_generation(db_path)
        if generation is None:
            print("No DB in GCS — nothing to repair.")
            return
        print(f"Pulled DB at generation {generation}\n")

        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        try:
            init_db(engine)
            with Session(engine) as session:
                changes = plan_and_apply(session, apply=args.apply)
        finally:
            engine.dispose()

        print()
        if changes == 0:
            print("Nothing to change — GCS roster is already canonical.")
            return
        if not args.apply:
            print(f"DRY RUN — {changes} change(s) planned. Re-run with --apply to write to GCS.")
            return

        # Compare-and-swap, same as the runtime writer: refuse to clobber a
        # concurrent ingest that landed while we were editing.
        if storage_manager.upload_db_if_unchanged(db_path, generation):
            print(f"Applied {changes} change(s) and pushed to GCS.")
        else:
            print("ABORTED — GCS moved while we were editing (a stream was ingested). Re-run.")
            sys.exit(1)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
