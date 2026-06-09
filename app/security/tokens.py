"""API token generation and hashing."""

import hashlib
import secrets

# Token format:  wm_<prefix>_<secret>
# prefix: 8 random hex chars (shown in UI for identification)
# secret: 40 random hex chars (never stored; only the SHA-256 hash is stored)

TOKEN_PREFIX_LEN = 8
TOKEN_SECRET_LEN = 40
TOKEN_SCHEME = "wm"


def generate_token() -> tuple[str, str, str]:
    """Return (raw_token, prefix, token_hash).

    raw_token is shown to the user once and never stored.
    token_hash (SHA-256) is stored in the database.
    prefix is the human-readable identifier shown in the UI.
    """
    prefix = secrets.token_hex(TOKEN_PREFIX_LEN // 2)
    secret = secrets.token_hex(TOKEN_SECRET_LEN // 2)
    raw = f"{TOKEN_SCHEME}_{prefix}_{secret}"
    token_hash = _hash_token(raw)
    return raw, prefix, token_hash


def hash_token(raw: str) -> str:
    return _hash_token(raw)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
