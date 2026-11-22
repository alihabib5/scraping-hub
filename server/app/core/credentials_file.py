"""The encrypted credentials file the installed Windows app reads.

Portal logins never ship inside the app. They live in a separate file —
`credentials.shc` in C:\\ProgramData\\Scraping Hub — that the setup wizard asks
for. It is made on the developer's PC by installer/make_credentials.py from a
.env, and only an app built with the matching key (installer/credentials.key,
compiled into the exe) can open it.

Locked to the PC: the first time the app opens the file it was given (a
portable "SHC1" file), it rewrites the installed copy as "SHM1" — the same
bytes wrapped with Windows DPAPI in machine scope, using the app key as extra
entropy. That copy opens only on this PC and only with this build, so copying
C:\\ProgramData\\Scraping Hub to another computer gets nothing usable.

Honest limit: the key ships inside the exe, so this keeps the passwords from
being read off the disk or carried to another PC, not from a determined
reverse-engineer working on this PC.
Stdlib only: an HMAC-SHA256 keystream plus an HMAC tag. Import-light on
purpose — the entry point loads it before the app's settings exist.
"""

import hashlib
import hmac
import json
import os
import secrets
import sys
from pathlib import Path

MAGIC = b"SHC1"
BOUND_MAGIC = b"SHM1"
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


# -- Locking the installed copy to this PC (Windows DPAPI, machine scope) -----


def _dpapi(data: bytes, entropy: bytes, protect: bool) -> bytes:
    """CryptProtectData / CryptUnprotectData, machine scope. OSError when Windows refuses."""
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(b: bytes) -> Blob:
        buf = ctypes.create_string_buffer(b, len(b))
        return Blob(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))

    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    flags = 0x4 | 0x1  # CRYPTPROTECT_LOCAL_MACHINE | CRYPTPROTECT_UI_FORBIDDEN
    src, ent, out = blob(data), blob(entropy), Blob()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    args = (ctypes.byref(src), None, ctypes.byref(ent), None, None, flags, ctypes.byref(out))
    if not fn(*args):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def can_bind() -> bool:
    return sys.platform == "win32"


def bind_to_this_pc(data: bytes, key: bytes) -> bytes:
    """A portable SHC1 file -> an SHM1 file that opens only on this PC."""
    return BOUND_MAGIC + _dpapi(data, key, protect=True)


def open_bytes(data: bytes, key: bytes) -> dict[str, str]:
    """The values in a portable (SHC1) or PC-locked (SHM1) file; ValueError if it can't be opened here."""
    if data[:4] == BOUND_MAGIC:
        if not can_bind():
            raise ValueError("credentials file is locked to a Windows PC")
        try:
            data = _dpapi(data[4:], key, protect=False)
        except OSError:
            raise ValueError(
                "this credentials file is locked to another PC; choose the .shc file you were sent"
            ) from None
    return decrypt(data, key)


def load_and_lock(path: Path, key: bytes) -> tuple[dict[str, str], bool]:
    """Open the installed file and, if it is still portable, lock it to this PC in place.

    Returns (values, locked_now). Locking is best effort: when the rewrite fails
    the values are still returned and the next start tries again.
    """
    data = path.read_bytes()
    values = open_bytes(data, key)
    if data[:4] != MAGIC or not can_bind():
        return values, False
    try:
        bound = bind_to_this_pc(data, key)
        if open_bytes(bound, key) != values:  # never replace a file with one that doesn't read back
            return values, False
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(bound)
        os.replace(tmp, path)
        return values, True
    except OSError:
        return values, False
