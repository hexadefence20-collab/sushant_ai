import hashlib
import hmac
import json
import time

from .config import SECRET_KEY


def _b64encode(raw: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64decode(data: str) -> bytes:
    import base64
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def issue_token(payload: dict, ttl: int) -> str:
    p = dict(payload)
    p["_exp"] = int(time.time()) + ttl
    body = _b64encode(json.dumps(p).encode())
    sig = hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_token(token: str) -> dict | None:
    try:
        body, sig = token.split(".")
        expect = hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expect, sig):
            return None
        payload = json.loads(_b64decode(body))
        if payload.get("_exp", 0) < int(time.time()):
            return None
        return payload
    except Exception:
        return None