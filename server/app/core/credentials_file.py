"""The encrypted credentials file the installed Windows app reads.

Portal logins never ship inside the app. They live in a separate file —
`credentials.shc` in C:\\ProgramData\\Scraping Hub — that the setup wizard asks
for. It is made on the developer's PC by installer/make_credentials.py from a
.env, and only an app built with the matching key (installer/credentials.key,
compiled into the exe) can open it.

Honest limit: the key ships inside the exe, so this keeps the passwords from
being read off the disk, not from a determined reverse-engineer.
Stdlib only: an HMAC-SHA256 keystream plus an HMAC tag. Import-light on
purpose — the entry point loads it before the app's settings exist.
"""

import hashlib
import hmac
import json
import secrets

MAGIC = b"SHC1"
FILE_NAME = "credentials.shc"


def _stream(key: bytes, nonce: bytes, n: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < n:
        out += hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        counter += 1
    return bytes(out[:n])


def encrypt(values: dict[str, str], key: bytes) -> bytes:
    nonce = secrets.token_bytes(16)
    plain = json.dumps(values).encode("utf-8")
    body = bytes(a ^ b for a, b in zip(plain, _stream(key, nonce, len(plain))))
    tag = hmac.new(key, MAGIC + nonce + body, hashlib.sha256).digest()
    return MAGIC + nonce + tag + body


def decrypt(data: bytes, key: bytes) -> dict[str, str]:
    """The values in `data`; ValueError if it is not a credentials file for this key."""
    if data[:4] != MAGIC or len(data) < 52:
        raise ValueError("not a Scraping Hub credentials file")
    nonce, tag, body = data[4:20], data[20:52], data[52:]
    if not hmac.compare_digest(tag, hmac.new(key, MAGIC + nonce + body, hashlib.sha256).digest()):
        raise ValueError("credentials file was made for a different build, or is damaged")
    plain = bytes(a ^ b for a, b in zip(body, _stream(key, nonce, len(body))))
    return json.loads(plain.decode("utf-8"))
