from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

import pyotp
from fastapi import HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from services.config_store import get_config_value, set_config_value

AUTH_STATE_KEY = "_browser_auth_state"
COOKIE_NAME = "healthquery_session"
SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
SIGNING_SALT = "healthquery-browser-session"


@dataclass(frozen=True)
class BrowserAuthState:
    totp_secret: str
    enrolled: bool
    session_secret: str


async def load_browser_auth_state() -> BrowserAuthState:
    raw = await get_config_value(AUTH_STATE_KEY, default={})
    raw = raw if isinstance(raw, dict) else {}
    return BrowserAuthState(
        totp_secret=str(raw.get("totp_secret", "")),
        enrolled=bool(raw.get("enrolled", False)),
        session_secret=str(raw.get("session_secret", "")),
    )


async def ensure_browser_auth_state() -> BrowserAuthState:
    state = await load_browser_auth_state()
    if state.totp_secret and state.session_secret:
        return state
    state = BrowserAuthState(
        totp_secret=state.totp_secret or pyotp.random_base32(),
        enrolled=state.enrolled,
        session_secret=state.session_secret or secrets.token_urlsafe(48),
    )
    await set_config_value(
        AUTH_STATE_KEY,
        {
            "totp_secret": state.totp_secret,
            "enrolled": state.enrolled,
            "session_secret": state.session_secret,
        },
    )
    return state


async def enroll_browser_auth() -> BrowserAuthState:
    state = await ensure_browser_auth_state()
    enrolled = BrowserAuthState(
        totp_secret=state.totp_secret,
        enrolled=True,
        session_secret=state.session_secret,
    )
    await set_config_value(
        AUTH_STATE_KEY,
        {
            "totp_secret": enrolled.totp_secret,
            "enrolled": enrolled.enrolled,
            "session_secret": enrolled.session_secret,
        },
    )
    return enrolled


def _serializer(session_secret: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(session_secret, salt=SIGNING_SALT)


def _is_https(request: Request) -> bool:
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


async def session_is_valid(request: Request) -> bool:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return False
    state = await ensure_browser_auth_state()
    try:
        _serializer(state.session_secret).loads(token, max_age=SESSION_MAX_AGE_SECONDS)
        return True
    except (BadSignature, SignatureExpired):
        return False


async def require_browser_session(request: Request) -> None:
    if not await session_is_valid(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


async def issue_session_cookie(request: Request, response: Response) -> None:
    state = await ensure_browser_auth_state()
    token = _serializer(state.session_secret).dumps({"authenticated": True, "issued_at": int(time.time())})
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=_is_https(request),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/")
