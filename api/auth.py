"""
api/auth.py
────────────
Azure Active Directory (Entra ID) JWT authentication for FastAPI.

All API endpoints require a valid Bearer token issued by the EY Azure AD tenant.
The token is validated against Microsoft's JWKS endpoint (public keys).
User identity (UPN, object ID) is extracted for audit logging and
document-level access control.

For Teams Copilot: Teams performs SSO and passes the user token automatically.
"""

from __future__ import annotations

import time
from functools import lru_cache

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from jose.backends import RSAKey

from config.settings import get_settings

settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)


class AzureADAuth:
    """
    Validates Azure AD JWT tokens.

    Token validation steps:
    1. Fetch JWKS from Microsoft (cached for 1 hour).
    2. Decode and verify signature, issuer, audience, and expiry.
    3. Return claims dict including UPN and object_id.
    """

    JWKS_URL = (
        "https://login.microsoftonline.com/"
        "{tenant_id}/discovery/v2.0/keys"
    )
    ISSUER   = "https://login.microsoftonline.com/{tenant_id}/v2.0"

    def __init__(self) -> None:
        self._jwks_cache: dict | None = None
        self._jwks_fetched_at: float  = 0.0

    async def _get_jwks(self) -> dict:
        """Fetch and cache Microsoft JWKS (public keys)."""
        now = time.time()
        if self._jwks_cache and now - self._jwks_fetched_at < 3600:
            return self._jwks_cache

        url = self.JWKS_URL.format(tenant_id=settings.azure_tenant_id)
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10)
            resp.raise_for_status()
        self._jwks_cache = resp.json()
        self._jwks_fetched_at = now
        return self._jwks_cache

    async def validate_token(self, token: str) -> dict:
        """
        Validate an Azure AD JWT and return its claims.
        Raises HTTPException 401 if invalid.
        """
        try:
            jwks    = await self._get_jwks()
            issuer  = self.ISSUER.format(tenant_id=settings.azure_tenant_id)
            claims  = jwt.decode(
                token,
                jwks,
                algorithms=["RS256"],
                audience=settings.azure_ad_audience,
                issuer=issuer,
                options={"verify_exp": True},
            )
            return claims
        except JWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {exc}",
                headers={"WWW-Authenticate": "Bearer"},
            )


# ── FastAPI dependency ────────────────────────────────────────────────────────

_auth = AzureADAuth()


async def get_current_user(token: str | None = Depends(oauth2_scheme)) -> dict:
    """
    FastAPI dependency that validates the bearer token and returns user claims.
    In development (APP_ENV=development), auth is bypassed for convenience.
    """
    if settings.app_env == "development":
        # Bypass auth in local dev
        return {"upn": "dev@ey.com", "oid": "dev-user-id", "name": "Dev User"}

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = await _auth.validate_token(token)
    return {
        "upn":  claims.get("upn") or claims.get("preferred_username", ""),
        "oid":  claims.get("oid", ""),
        "name": claims.get("name", ""),
    }
