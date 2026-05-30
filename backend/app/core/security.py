import os
import hashlib
import hmac
import base64
import json
import time

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production")

def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{h}"

def verify_password(password: str, hashed: str) -> bool:
    try:
        salt, h = hashed.split(":", 1)
        return hmac.compare_digest(h, hashlib.sha256((salt + password).encode()).hexdigest())
    except Exception:
        return False

def create_token(user_id: int, username: str) -> str:
    payload = {"sub": username, "uid": user_id, "exp": int(time.time()) + 86400}
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    mac = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256)
    sig = mac.hexdigest()
    return f"{payload_b64}.{sig}"

def decode_token(token: str) -> dict | None:
    try:
        payload_b64, sig = token.rsplit(".", 1)
        mac = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256)
        expected = mac.hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None
