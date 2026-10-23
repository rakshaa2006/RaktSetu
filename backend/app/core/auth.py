"""Authentication and demo identity resolution for blood bank workflows.

IMPORTANT NOTICE:
Demo credentials and tokens do not verify real blood bank employees or staff.
They are provided solely for hackathon demonstration, automated testing, and
decision-support simulations. They MUST NOT be used in production environments.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException, status

from app.core.config import get_settings


def get_authenticated_bank_id(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> str:
    """Extract and validate the Bearer token from the Authorization header.

    Derives the blood bank ID strictly from the configured token map.
    Fails closed (401 Unauthorized) if configuration is missing, token is omitted,
    or the token is invalid/unknown.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Bearer token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.strip().split(maxsplit=1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization format. Expected 'Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty bearer token provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = get_settings()
    demo_tokens = settings.demo_tokens

    # Fail closed if no demo tokens are configured
    if not demo_tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No blood bank demo identities configured on this server.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    bank_id = demo_tokens.get(token)
    if not bank_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or unrecognized blood bank bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return bank_id


def verify_bank_identity(
    bank_id: str,
    authenticated_bank_id: str = Depends(get_authenticated_bank_id),
) -> str:
    """Enforce bank isolation: verify that the token owner matches the path bank_id."""
    if authenticated_bank_id != bank_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: Authenticated as '{authenticated_bank_id}', not authorized for '{bank_id}'.",
        )
    return authenticated_bank_id
