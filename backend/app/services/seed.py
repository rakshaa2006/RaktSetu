"""Idempotent loading of the fictional demonstration CSV files.

* Existing rows are never duplicated or modified (unless refresh_timestamps=True,
  which only re-bases last-updated times).
* Request history is never touched.
* CSV column `last_updated_hours_ago`: number = that many hours before seeding,
  blank = missing timestamp, INVALID = deliberately unreadable timestamp.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.rules import (BLOOD_GROUPS, COMPONENTS, CONSENT_STATUSES, DONOR_RESPONSE_STATUSES,
                            RECORD_STATUSES)
from app.models import BloodBank, Donor

BANK_COLUMNS = ["bank_id", "name", "location", "latitude", "longitude", "blood_group", "component",
                "units_available", "availability_status", "last_updated_hours_ago", "data_source"]
DONOR_COLUMNS = ["donor_id", "display_name", "blood_group", "location", "latitude", "longitude",
                 "consent_status", "availability_status", "response_status", "last_updated_hours_ago", "data_source"]
LOCATION_COLUMNS = ["location_id", "name", "latitude", "longitude"]
INVALID_TIMESTAMP_TEXT = "not-a-timestamp"


@dataclass
class SeedReport:
    banks_added: int = 0
    banks_skipped: int = 0
    donors_added: int = 0
    donors_skipped: int = 0
    timestamps_refreshed: int = 0
    notes: List[str] = field(default_factory=list)


def _read_csv(path: Path, expected: List[str]) -> List[Dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Demo data file not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in expected if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path.name}: missing column(s) {missing}")
        return [{k: (v or "").strip() for k, v in row.items()} for row in reader]


def _float(value: str, what: str, row_no: int, lo: float, hi: float) -> Optional[float]:
    if value == "":
        return None
    try:
        number = float(value)
    except ValueError:
        raise ValueError(f"Row {row_no}: {what} '{value}' is not a number")
    if not lo <= number <= hi:
        raise ValueError(f"Row {row_no}: {what} {number} is out of range")
    return number


def _choice(value: str, allowed, what: str, row_no: int) -> str:
    if value not in allowed:
        raise ValueError(f"Row {row_no}: {what} '{value}' must be one of {list(allowed)}")
    return value


def _timestamp(hours_ago: str, now: datetime, row_no: int) -> Optional[str]:
    if hours_ago == "":
        return None
    if hours_ago.upper() == "INVALID":
        return INVALID_TIMESTAMP_TEXT
    try:
        return (now - timedelta(hours=float(hours_ago))).isoformat()
    except ValueError:
        raise ValueError(f"Row {row_no}: last_updated_hours_ago '{hours_ago}' must be a number, blank or INVALID")


def load_locations(data_dir: Path) -> List[Dict[str, object]]:
    rows = _read_csv(Path(data_dir) / "demo_locations.csv", LOCATION_COLUMNS)
    out = []
    for n, r in enumerate(rows, start=2):
        out.append({
            "location_id": r["location_id"], "name": r["name"],
            "latitude": _float(r["latitude"], "latitude", n, -90, 90),
            "longitude": _float(r["longitude"], "longitude", n, -180, 180),
        })
    return out


def seed_database(db: Session, data_dir: Path, now: Optional[datetime] = None,
                  refresh_timestamps: bool = False) -> SeedReport:
    """Validate and load the CSVs. On any bad row nothing is written."""
    try:
        return _seed(db, data_dir, now, refresh_timestamps)
    except Exception:
        db.rollback()
        raise


def _seed(db: Session, data_dir: Path, now: Optional[datetime], refresh_timestamps: bool) -> SeedReport:
    now = now or datetime.now(timezone.utc)
    data_dir = Path(data_dir)
    report = SeedReport()
    bank_rows = _read_csv(data_dir / "demo_blood_banks.csv", BANK_COLUMNS)
    donor_rows = _read_csv(data_dir / "demo_donors.csv", DONOR_COLUMNS)

    seen = set()
    for n, r in enumerate(bank_rows, start=2):
        bid = r["bank_id"]
        if not bid or bid in seen:
            raise ValueError(f"demo_blood_banks.csv row {n}: bank_id missing or duplicated")
        seen.add(bid)
        units = r["units_available"]
        if not units.isdigit():
            raise ValueError(f"demo_blood_banks.csv row {n}: units_available must be a whole number >= 0")
        values = dict(
            name=r["name"], location=r["location"],
            latitude=_float(r["latitude"], "latitude", n, -90, 90),
            longitude=_float(r["longitude"], "longitude", n, -180, 180),
            blood_group=_choice(r["blood_group"], BLOOD_GROUPS, "blood_group", n),
            component=_choice(r["component"], COMPONENTS, "component", n),
            units_available=int(units),
            availability_status=_choice(r["availability_status"], RECORD_STATUSES, "availability_status", n),
            last_updated=_timestamp(r["last_updated_hours_ago"], now, n),
            data_source=r["data_source"], is_simulated=True,
        )
        existing = db.get(BloodBank, bid)
        if existing is None:
            db.add(BloodBank(id=bid, **values))
            report.banks_added += 1
        else:
            report.banks_skipped += 1
            if refresh_timestamps:
                existing.last_updated = values["last_updated"]
                report.timestamps_refreshed += 1

    seen = set()
    for n, r in enumerate(donor_rows, start=2):
        did = r["donor_id"]
        if not did or did in seen:
            raise ValueError(f"demo_donors.csv row {n}: donor_id missing or duplicated")
        seen.add(did)
        values = dict(
            display_name=r["display_name"], location=r["location"],
            latitude=_float(r["latitude"], "latitude", n, -90, 90),
            longitude=_float(r["longitude"], "longitude", n, -180, 180),
            blood_group=_choice(r["blood_group"], BLOOD_GROUPS, "blood_group", n),
            consent_status=_choice(r["consent_status"], CONSENT_STATUSES, "consent_status", n),
            availability_status=_choice(r["availability_status"], RECORD_STATUSES, "availability_status", n),
            response_status=_choice(r["response_status"], DONOR_RESPONSE_STATUSES, "response_status", n),
            last_updated=_timestamp(r["last_updated_hours_ago"], now, n),
            data_source=r["data_source"], is_simulated=True,
        )
        existing = db.get(Donor, did)
        if existing is None:
            db.add(Donor(id=did, **values))
            report.donors_added += 1
        else:
            report.donors_skipped += 1
            if refresh_timestamps:
                existing.last_updated = values["last_updated"]
                report.timestamps_refreshed += 1
    db.commit()
    return report
