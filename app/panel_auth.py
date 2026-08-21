"""Iris — panel pairing password (Argon2id).

The panel password is set/changed from the PC (Settings > Network) and stored
only as an Argon2id PHC hash in iris_config.json. It is never returned by any
API and never placed in the QR code or client-side storage. Phones pair by
entering the password at /login; each successful entry mints a persistent
device session exactly like the old QR-token flow.

If argon2-cffi is unavailable the password feature is simply disabled —
pairing is refused with a clear message, and the app keeps running.
"""

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerificationError, VerifyMismatchError
    _HASHER = PasswordHasher()
    _AVAILABLE = True
except Exception:  # pragma: no cover - argon2 missing
    _HASHER = None
    _AVAILABLE = False

# Config key that stores the Argon2id PHC string (server-side only).
PANEL_PASSWORD_KEY = "panel_password_hash"

# Minimum accepted password length.
MIN_PASSWORD_LEN = 4


def password_available():
    """True when argon2-cffi is importable and the feature can be used."""
    return _AVAILABLE


def hash_password(password):
    """Hash a plaintext password with Argon2id (random salt, PHC string)."""
    if not _AVAILABLE:
        raise RuntimeError("argon2 not available")
    return _HASHER.hash(password)


def verify_password(stored, password):
    """Constant-time verification of a plaintext password against a PHC hash."""
    if not _AVAILABLE or not stored:
        return False
    try:
        return _HASHER.verify(stored, password)
    except (VerifyMismatchError, VerificationError):
        return False
    except Exception:
        return False


def is_phc_hash(value):
    """True when value looks like an Argon2id PHC string."""
    return isinstance(value, str) and value.startswith("$argon2id$")
