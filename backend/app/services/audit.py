"""Append-only event history. There is deliberately no update or delete function.

This is an application-level log. It is not tamper-proof or legally certified.
Messages must never contain patient name, age, gender or blood group.
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import utcnow
from app.models import AuditEvent


def record_event(db: Session, request_id: str, event_type: str, reason: str,
                 candidate_type: Optional[str] = None, candidate_id: Optional[str] = None,
                 previous_state: Optional[str] = None, new_state: Optional[str] = None,
                 is_simulation: bool = False) -> AuditEvent:
    """Add an event to the session. The caller commits so state and history change together."""
    event = AuditEvent(
        event_id="EVT-" + uuid.uuid4().hex[:10].upper(), request_id=request_id, event_type=event_type,
        timestamp=utcnow(), candidate_type=candidate_type, candidate_id=candidate_id,
        previous_state=previous_state, new_state=new_state, reason=reason, is_simulation=is_simulation,
    )
    db.add(event)
    db.flush()
    return event


def get_timeline(db: Session, request_id: str) -> List[AuditEvent]:
    """Oldest first; ties broken by insertion order."""
    return list(db.scalars(
        select(AuditEvent).where(AuditEvent.request_id == request_id)
        .order_by(AuditEvent.timestamp.asc(), AuditEvent.seq.asc())
    ))


def recent_events(db: Session, limit: int = 8) -> List[AuditEvent]:
    return list(db.scalars(select(AuditEvent).order_by(AuditEvent.seq.desc()).limit(limit)))
