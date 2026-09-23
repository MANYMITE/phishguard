"""Safety invariants: storage guard, input validation, anti-theft assertion.

Three jobs:

1. `is_credential_field` / `sanitize_fields` — the storage layer refuses
   credential-shaped data (README invariant 2).
2. Input validators — every admin-supplied string is length-limited and
   shape-checked before it reaches the database.
3. `assert_no_password_fields` — a helper templates/tests can call to prove
   a simulation form is credential-safe by construction.
"""
import re

# Matches common credential-shaped field names anywhere in a key.
CREDENTIAL_FIELD_RE = re.compile(
    r"(pass(word|wd|wort)?|pwd|pin|otp|secret|token|credential)", re.IGNORECASE
)

# The exact set a realistic login form uses for its password box. The test
# suite asserts NONE of these names is submitted anywhere by our templates.
PASSWORD_FIELD_NAMES = ("password", "passwd", "pwd", "user_password",
                        "login_password", "confirm_password")

NAME_MAX_LEN = 80
EMAIL_MAX_LEN = 254

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ValidationError(ValueError):
    """Raised when user-supplied input fails validation."""


class CredentialStorageError(ValueError):
    """Raised when something tries to persist credential-shaped data."""


def is_credential_field(key: str) -> bool:
    return bool(CREDENTIAL_FIELD_RE.search(key or ""))


def sanitize_fields(fields: dict) -> dict:
    """Return only safe, explicitly allowed metadata from a submitted form.

    Credential-shaped keys are never returned; unknown keys are dropped too.
    """
    return {
        k: v for k, v in fields.items()
        if not is_credential_field(k) and k in _ALLOWED_METADATA
    }


def assert_no_password_fields(form_field_names) -> None:
    """Raise CredentialStorageError if any password-shaped field is present.

    Used by tests as a structural assertion: our simulation forms must not
    even HAVE a password field to be safe — they do, for realism — so this
    helper is for verifying *storage* paths never accept such fields.
    """
    for name in form_field_names or ():
        if name in PASSWORD_FIELD_NAMES or is_credential_field(name):
            raise CredentialStorageError(
                f"refusing to handle credential-shaped field: {name}"
            )


# ---------------------------------------------------------------------------
# Input validation (admin-supplied strings)
# ---------------------------------------------------------------------------

def _clean_text(raw: str, max_len: int) -> str:
    return " ".join((raw or "").split())[:max_len]


def validate_campaign_name(raw: str) -> str:
    name = _clean_text(raw, NAME_MAX_LEN)
    if len(name) < 3:
        raise ValidationError("Campaign name needs at least 3 characters.")
    return name


def validate_participant_name(raw: str) -> str:
    name = _clean_text(raw, NAME_MAX_LEN)
    if len(name) < 2:
        raise ValidationError("Participant name needs at least 2 characters.")
    return name


def validate_email(raw: str) -> str:
    email = (raw or "").strip().lower()[:EMAIL_MAX_LEN]
    if not _EMAIL_RE.match(email):
        raise ValidationError("Enter a valid email address.")
    return email


_ALLOWED_METADATA: set[str] = {"user_agent", "template_key", "campaign_id"}
