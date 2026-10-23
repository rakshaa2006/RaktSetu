"""REST endpoints. Every endpoint reads or writes the real database."""
from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import FRESHNESS
from app.core.errors import NotFoundError, RuleViolation
from app.core.geo import distance_km
from app.core.rules import (BLOOD_GROUPS, CANDIDATE_STATUSES, CANDIDATE_TRANSITIONS, COMPONENTS, GENDERS,
                            MATCH_RULES_DOC, REQUEST_STATUSES, REQUEST_TRANSITIONS, URGENCIES)
from app.database import get_db, utcnow
from app.models import AuditEvent, BloodBank, BloodRequest, Donor, RankingSnapshot
from app.schemas.schemas import (AuditEventOut, BloodBankOut, BloodGroup, Component, DashboardOut, DonorOut,
                                 EventCreate, EventResultOut, HealthOut, LocationOut, MetaOut,
                                 RecommendationsOut, RequestCreate, RequestOut, SnapshotOut, SnapshotSummary,
                                 StatusUpdate)
from app.services import audit, coordination
from app.services.freshness import LABEL_LEGEND, assess_freshness, verification_label
from app.services.ranking import DISCLAIMER
from app.services.recovery import EVENT_RULES
from app.services.seed import load_locations

router = APIRouter(prefix="/api")

ACTIVE_STATUSES = ("open", "under_review", "awaiting_confirmation", "partially_fulfilled")


# ------------------------------------------------------------------ helpers
def _freshness_dict(rec, now, near):
    fr = assess_freshness(rec.last_updated, now)
    dist = distance_km(near[0], near[1], rec.latitude, rec.longitude) if near else None
    if near is None:
        note = "Choose a location to see distance."
    elif dist is None:
        note = "Distance unknown: coordinates are missing."
    else:
        note = "Straight-line distance, not road distance or travel time."
    return {
        "freshness": fr.freshness, "age_hours": fr.age_hours, "freshness_note": fr.note,
        "verification_label": verification_label(rec.availability_status, fr.freshness),
        "distance_km": dist, "distance_note": note,
    }


def _near(near_lat: Optional[float], near_lng: Optional[float]):
    if (near_lat is None) != (near_lng is None):
        raise RuleViolation("Provide both near_lat and near_lng, or neither.")
    return None if near_lat is None else (near_lat, near_lng)


def _sorted(items, near):
    if near is None:
        return items
    return sorted(items, key=lambda i: (i.distance_km is None, i.distance_km or 0.0, i.id))


def _snapshot_out(snap: RankingSnapshot) -> SnapshotOut:
    p = snap.payload
    return SnapshotOut(version=snap.version, trigger=snap.trigger, created_at=snap.created_at,
                       summary=p["summary"], ranked=p["ranked"], excluded=p["excluded"], changes=p["changes"])


def _recommendations(db: Session, req: BloodRequest, version: Optional[int] = None) -> RecommendationsOut:
    snaps = list(db.scalars(select(RankingSnapshot).where(RankingSnapshot.request_id == req.id)
                            .order_by(RankingSnapshot.version.desc())))
    if not snaps:
        snaps = [coordination.generate_snapshot(db, req, trigger="First view")]
        db.commit()
    current = snaps[0]
    if version is not None:
        found = [s for s in snaps if s.version == version]
        if not found:
            raise NotFoundError(f"Ranking version {version} does not exist for this request.")
        current = found[0]
    history = []
    for s in snaps:
        ranked = s.payload["ranked"]
        top = ranked[0] if ranked else None
        history.append(SnapshotSummary(
            version=s.version, trigger=s.trigger, created_at=s.created_at, ranked_count=len(ranked),
            excluded_count=len(s.payload["excluded"]), top_candidate_id=top["candidate_id"] if top else None,
            top_candidate_name=top["display_name"] if top else None, changes=s.payload["changes"]))
    return RecommendationsOut(request_id=req.id, current=_snapshot_out(current), history=history)


# ------------------------------------------------------------------- system
@router.get("/health", response_model=HealthOut, tags=["system"])
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return HealthOut(status="ok", service="RaktSetu", database="ok", demo_data=True, time=utcnow())


@router.get("/meta", response_model=MetaOut, tags=["system"])
def meta():
    labels = {k: r.label for k, r in EVENT_RULES.items()}
    labels["COORDINATOR_NOTE"] = "Record a coordinator note"
    return MetaOut(
        blood_groups=list(BLOOD_GROUPS), components=list(COMPONENTS), genders=list(GENDERS),
        urgencies=list(URGENCIES), request_statuses=list(REQUEST_STATUSES),
        candidate_statuses=list(CANDIDATE_STATUSES),
        request_transitions={k: sorted(v) for k, v in REQUEST_TRANSITIONS.items()},
        candidate_transitions={k: sorted(v) for k, v in CANDIDATE_TRANSITIONS.items()},
        event_types=labels, freshness_recent_hours=FRESHNESS.recent_hours, freshness_legend=LABEL_LEGEND,
        match_rules=MATCH_RULES_DOC, disclaimer=DISCLAIMER)


@router.get("/locations", response_model=List[LocationOut], tags=["records"])
def locations(request: Request):
    return load_locations(request.app.state.data_dir)


# ------------------------------------------------------------------ records
@router.get("/blood-banks", response_model=List[BloodBankOut], tags=["records"])
def blood_banks(near_lat: Optional[float] = Query(None, ge=-90, le=90),
                near_lng: Optional[float] = Query(None, ge=-180, le=180),
                blood_group: Optional[BloodGroup] = None, component: Optional[Component] = None,
                db: Session = Depends(get_db)):
    near, now = _near(near_lat, near_lng), utcnow()
    stmt = select(BloodBank).order_by(BloodBank.id)
    if blood_group:
        stmt = stmt.where(BloodBank.blood_group == blood_group)
    if component:
        stmt = stmt.where(BloodBank.component == component)
    out = [BloodBankOut(id=b.id, name=b.name, location=b.location, latitude=b.latitude, longitude=b.longitude,
                        blood_group=b.blood_group, component=b.component, units_available=b.units_available,
                        availability_status=b.availability_status, last_updated=b.last_updated,
                        data_source=b.data_source, is_simulated=b.is_simulated, **_freshness_dict(b, now, near))
           for b in db.scalars(stmt)]
    return _sorted(out, near)


@router.get("/donors", response_model=List[DonorOut], tags=["records"])
def donors(near_lat: Optional[float] = Query(None, ge=-90, le=90),
           near_lng: Optional[float] = Query(None, ge=-180, le=180),
           blood_group: Optional[BloodGroup] = None, db: Session = Depends(get_db)):
    near, now = _near(near_lat, near_lng), utcnow()
    stmt = select(Donor).order_by(Donor.id)
    if blood_group:
        stmt = stmt.where(Donor.blood_group == blood_group)
    out = [DonorOut(id=d.id, display_name=d.display_name, blood_group=d.blood_group, location=d.location,
                    latitude=d.latitude, longitude=d.longitude, consent_status=d.consent_status,
                    availability_status=d.availability_status, response_status=d.response_status,
                    last_updated=d.last_updated, data_source=d.data_source, is_simulated=d.is_simulated,
                    **_freshness_dict(d, now, near))
           for d in db.scalars(stmt)]
    return _sorted(out, near)


# ----------------------------------------------------------------- requests
@router.get("/requests", response_model=List[RequestOut], tags=["requests"])
def list_requests(db: Session = Depends(get_db)):
    return list(db.scalars(select(BloodRequest).order_by(BloodRequest.created_at.desc(), BloodRequest.id)))


@router.post("/requests", response_model=RequestOut, status_code=201, tags=["requests"])
def create_request(payload: RequestCreate, db: Session = Depends(get_db)):
    return coordination.create_request(db, payload)


@router.get("/requests/{request_id}", response_model=RequestOut, tags=["requests"])
def get_request(request_id: str, db: Session = Depends(get_db)):
    return coordination.get_request_or_404(db, request_id)


@router.get("/requests/{request_id}/recommendations", response_model=RecommendationsOut, tags=["requests"])
def get_recommendations(request_id: str, version: Optional[int] = Query(None, ge=1),
                        db: Session = Depends(get_db)):
    req = coordination.get_request_or_404(db, request_id)
    return _recommendations(db, req, version)


@router.post("/requests/{request_id}/recommendations/recalculate", response_model=RecommendationsOut,
             status_code=201, tags=["requests"])
def recalculate(request_id: str, db: Session = Depends(get_db)):
    req = coordination.get_request_or_404(db, request_id)
    coordination.recalculate(db, request_id)
    return _recommendations(db, req)


@router.get("/requests/{request_id}/timeline", response_model=List[AuditEventOut], tags=["requests"])
def timeline(request_id: str, db: Session = Depends(get_db)):
    coordination.get_request_or_404(db, request_id)
    return audit.get_timeline(db, request_id)


@router.post("/requests/{request_id}/events", response_model=EventResultOut, status_code=201, tags=["requests"])
def post_event(request_id: str, payload: EventCreate, db: Session = Depends(get_db)):
    event, _snap, req = coordination.process_event(db, request_id, payload.event_type, payload.candidate_type,
                                                    payload.candidate_id, payload.reason)
    return EventResultOut(event=AuditEventOut.model_validate(event), request=RequestOut.model_validate(req),
                          recommendations=_recommendations(db, req))


@router.patch("/requests/{request_id}/status", response_model=RequestOut, tags=["requests"])
def patch_status(request_id: str, payload: StatusUpdate, db: Session = Depends(get_db)):
    _event, req = coordination.update_status(db, request_id, payload.status, payload.reason,
                                             payload.simulated_confirmation)
    return req


# ---------------------------------------------------------------- dashboard
@router.get("/dashboard/summary", response_model=DashboardOut, tags=["system"])
def dashboard(db: Session = Depends(get_db)):
    now = utcnow()
    requests_ = list(db.scalars(select(BloodRequest).order_by(BloodRequest.created_at.desc(), BloodRequest.id)))
    by_status: Dict[str, int] = {}
    for r in requests_:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    active = [r for r in requests_ if r.status in ACTIVE_STATUSES]

    def label_counts(rows) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for rec in rows:
            lab = verification_label(rec.availability_status, assess_freshness(rec.last_updated, now).freshness)
            counts[lab] = counts.get(lab, 0) + 1
        return counts

    return DashboardOut(
        requests_total=len(requests_), requests_active=len(active),
        requests_urgent_active=sum(1 for r in active if r.urgency in ("Critical", "Urgent")),
        by_status=by_status,
        blood_banks=label_counts(db.scalars(select(BloodBank))),
        donors=label_counts(db.scalars(select(Donor))),
        recent_activity=audit.recent_events(db, 8), recent_requests=requests_[:5])
