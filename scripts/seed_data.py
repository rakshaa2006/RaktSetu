#!/usr/bin/env python
"""Load the fictional demo CSVs into the SQLite database.

Run from the project root (with the backend virtual environment active):

    python scripts/seed_data.py
    python scripts/seed_data.py --refresh-timestamps   # re-base 'last updated' times to now

Safe to run repeatedly: existing rows are skipped and request history is never touched.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.database import init_db, make_engine, make_session_factory  # noqa: E402
from app.services.seed import seed_database  # noqa: E402


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", default=settings.database_url, help="default: backend/raktsetu.db")
    parser.add_argument("--data-dir", default=str(settings.data_dir), help="default: data/")
    parser.add_argument("--refresh-timestamps", action="store_true",
                        help="reset last-updated times of existing demo rows relative to now")
    args = parser.parse_args()

    engine = make_engine(args.database_url)
    init_db(engine)
    with make_session_factory(engine)() as db:
        try:
            report = seed_database(db, Path(args.data_dir), refresh_timestamps=args.refresh_timestamps)
        except (ValueError, FileNotFoundError) as exc:
            print(f"Seeding failed, nothing was written: {exc}", file=sys.stderr)
            return 1
    print(f"Database: {args.database_url}")
    print(f"Blood banks: {report.banks_added} added, {report.banks_skipped} already present")
    print(f"Donors:      {report.donors_added} added, {report.donors_skipped} already present")
    if args.refresh_timestamps:
        print(f"Timestamps refreshed on {report.timestamps_refreshed} existing rows")
    print("All records are fictional demonstration data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
