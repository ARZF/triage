import base64
import hashlib
import hmac
import math
import secrets
from collections import OrderedDict, deque
from datetime import datetime
from threading import Lock

from app.core import db

N, R, P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=N, r=R, p=P)
    return "$".join(("scrypt", str(N), str(R), str(P),
                     base64.b64encode(salt).decode("ascii"), base64.b64encode(digest).decode("ascii")))


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt, expected = encoded.split("$")
        if (scheme, int(n), int(r), int(p)) != ("scrypt", N, R, P):
            return False
        salt = base64.b64decode(salt, validate=True)
        expected = base64.b64decode(expected, validate=True)
        if len(salt) != 16 or len(expected) != 64:
            return False
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=N, r=R, p=P)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, UnicodeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


DUMMY_HASH = hash_password(secrets.token_urlsafe(32))
# ponytail: bounded per-process login/password throttle (10000 keys); use a shared rate limiter with auth across workers.
FAILURES: OrderedDict[str, deque] = OrderedDict()
FAILURE_LOCK = Lock()
FAILURE_WINDOW = 15 * 60


def login_retry_after(username: str) -> int:
    now = datetime.fromisoformat(db.utc_now()).timestamp()
    with FAILURE_LOCK:
        failures = FAILURES.get(username)
        if failures is None:
            return 0
        while failures and failures[0] <= now - FAILURE_WINDOW:
            failures.popleft()
        if not failures:
            del FAILURES[username]
            return 0
        return max(1, math.ceil(failures[0] + FAILURE_WINDOW - now)) if len(failures) >= 5 else 0


def record_failure(username: str) -> None:
    now = datetime.fromisoformat(db.utc_now()).timestamp()
    with FAILURE_LOCK:
        if username not in FAILURES:
            if len(FAILURES) >= 10000:
                FAILURES.popitem(last=False)
            FAILURES[username] = deque()
        failures = FAILURES[username]
        while failures and failures[0] <= now - FAILURE_WINDOW:
            failures.popleft()
        failures.append(now)
        FAILURES.move_to_end(username)


def clear_failures(username: str) -> None:
    with FAILURE_LOCK:
        FAILURES.pop(username, None)
