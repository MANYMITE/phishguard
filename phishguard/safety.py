"""Safety invariants, enforced at the storage layer.

Invariant 2 of the README: the database layer REFUSES credential-shaped data.
Even if a future contributor adds a route that tries to log a password, the
write fails loudly instead of silently persisting secrets.
"""
import re

# Matches common credential-shaped field names anywhere in a key.
CREDENTIAL_FIELD_RE = re.compile(
    r"(pass(word|wd|wort)?|pwd|pin|otp|secret|token|credential)", re.IGNORECASE
)


class CredentialStorageError(ValueError):
    """Raised when something tries to persist credential-shaped data."""


def is_credential_field(key: str) -> bool:
    return bool(CREDENTIAL_FIELD_RE.search(key or ""))


def sanitize_fields(fields: dict) -> dict:
    """Return only safe, explicitly allowed metadata from a submitted form.

    Credential-shaped keys are never returned; unknown keys are dropped too.
    Callers may keep, at most, deliberately whitelisted harmless metadata.
    """
    return {
        k: v for k, v in fields.items()
        if not is_credential_field(k) and k in _ALLOWED_METADATA
    }


_ALLOWED_METADATA: set[str] = {"user_agent", "template_key", "campaign_id"}
