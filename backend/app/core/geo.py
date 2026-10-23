"""Straight-line (great-circle) distance. Never road distance or travel time."""
from __future__ import annotations

import math
from typing import Optional


def _valid(lat, lng) -> bool:
    try:
        return (
            lat is not None and lng is not None
            and not isinstance(lat, bool) and not isinstance(lng, bool)
            and math.isfinite(lat) and math.isfinite(lng)
            and -90 <= lat <= 90 and -180 <= lng <= 180
        )
    except TypeError:
        return False


def distance_km(lat1, lng1, lat2, lng2) -> Optional[float]:
    """Haversine distance in km rounded to 0.1, or None if any coordinate is missing/invalid."""
    if not (_valid(lat1, lng1) and _valid(lat2, lng2)):
        return None
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * r * math.asin(min(1.0, math.sqrt(a))), 1)
