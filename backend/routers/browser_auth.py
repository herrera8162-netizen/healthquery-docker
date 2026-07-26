from __future__ import annotations

import hmac

import pyotp
from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app_settings import get_settings
from services.browser_auth import (
    clear_session_cookie,
    enroll_browser_auth,
    ensure_browser_auth_state,
    issue_session_cookie,
    session_is_valid,
)

router = APIRouter(prefix="/api/auth", tags=["browser-auth"], include_in_schema=False)


class TotpCodeRequest(BaseModel):
    code: str = Field(..., pattern=r"^\d{6}$")


def _require_setup_token(provided: str) -> None:
    expected = get_settings().auth_setup_token
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Browser auth setup is not configured",
        )
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid setup token")


@router.get("/status")
async def auth_status() -> dict[str, bool]:
    state = await ensure_browser_auth_state()
    return {"enrolled": state.enrolled}


@router.get("/me")
async def auth_me(request: Request) -> dict[str, bool]:
    return {"authenticated": await session_is_valid(request)}


@router.get("/setup")
async def auth_setup(x_healthquery_setup_token: str = Header(default="")) -> dict[str, str]:
    _require_setup_token(x_healthquery_setup_token)
    state = await ensure_browser_auth_state()
    if state.enrolled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Already enrolled")
    uri = pyotp.TOTP(state.totp_secret).provisioning_uri(name="HealthQuery", issuer_name="HealthQuery")
    return {"secret": state.totp_secret, "otpauth_uri": uri}


@router.post("/setup/confirm")
async def confirm_auth_setup(
    body: TotpCodeRequest,
    request: Request,
    response: Response,
    x_healthquery_setup_token: str = Header(default=""),
) -> dict[str, bool]:
    _require_setup_token(x_healthquery_setup_token)
    state = await ensure_browser_auth_state()
    if state.enrolled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Already enrolled")
    if not pyotp.TOTP(state.totp_secret).verify(body.code, valid_window=1):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authenticator code")
    await enroll_browser_auth()
    await issue_session_cookie(request, response)
    return {"authenticated": True}


@router.post("/login")
async def auth_login(body: TotpCodeRequest, request: Request, response: Response) -> dict[str, bool]:
    state = await ensure_browser_auth_state()
    if not state.enrolled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Browser auth has not been enrolled")
    if not pyotp.TOTP(state.totp_secret).verify(body.code, valid_window=1):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authenticator code")
    await issue_session_cookie(request, response)
    return {"authenticated": True}


@router.post("/logout")
async def auth_logout(response: Response) -> dict[str, str]:
    clear_session_cookie(response)
    return {"status": "ok"}
