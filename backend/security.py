"""
AgriSmoke AI - Secret Redaction Utilities
Central helpers to strip credentials / API keys / tokens from log lines,
persisted error messages, and public API responses BEFORE they leave the
process. Fixing at the source means every downstream consumer (logs, DB,
HTTP responses, scheduler telemetry) receives already-safe strings.

No third-party dependencies.
"""

import os
import re
from typing import Iterable, List, Optional

# Credentials embedded in a URL userinfo section: scheme://user:pass@host
# (also matches redis://:pass@host and postgres://user:pass@host).
_CRED_IN_URL = re.compile(r"(\b[a-zA-Z][a-zA-Z0-9.+\-]*://)[^/@\s]*@")

# NASA FIRMS places the MAP_KEY as the path segment right after /csv/ in both
# the area and data-availability endpoints: /api/area/csv/<MAP_KEY>/<sensor>/...
_FIRMS_KEY_PATH = re.compile(r"(/api/(?:area|data_availability)/csv/)[^/]+/")

# Environment variables whose values are secrets. Anything derived from them
# (connection strings, MAP keys, tokens) must never reach logs, the database,
# or an HTTP response. Checked at call time so tests and dotenv reloads apply.
# The off-site backup targets (S3-compatible object storage) inject long-lived
# cloud credentials, so their secret keys are redacted from backup failure logs
# and the scheduler telemetry the same way as the data-provider secrets.
_SECRET_ENV_KEYS = (
    "NASA_FIRMS_MAP_KEY",
    "REDIS_URL",
    "DATABASE_URL",
    "AWS_SECRET_ACCESS_KEY",
    "OFFSITE_S3_SECRET_KEY",
    "BACKUP_S3_SECRET_KEY",
    "BACKUP_ENCRYPTION_KEY",
)


def known_env_secrets() -> List[str]:
    """Return the current values of all secret-bearing environment variables.

    Meant to be fed into :func:`redact_secrets` as extra literals so generic
    ``except Exception`` boundaries scrub every known credential in one call.
    """
    return [os.getenv(k, "").strip() for k in _SECRET_ENV_KEYS]


def mask_url(url: Optional[str]) -> str:
    """Return a copy of ``url`` with any ``scheme://credentials@`` userinfo masked.

    The host and path (without embedded secrets) are preserved so the value
    remains useful for diagnostics.
    """
    if not url:
        return url or ""
    return _CRED_IN_URL.sub(r"\1***@", url)


def redact_secrets(text: object, secrets: Optional[Iterable[str]] = None) -> Optional[str]:
    """Remove known secret literals and credential-bearing URL fragments.

    - Each literal in ``secrets`` (e.g. an API key / token) is replaced with
      ``***`` (longest first, so a key is not partially masked).
    - Any ``scheme://user:pass@`` userinfo is masked.
    - Any NASA FIRMS ``/csv/<MAP_KEY>/`` path segment is masked.

    ``None`` passes through unchanged so it can be used directly on optional
    error fields.
    """
    if text is None:
        return None
    out = str(text)

    literals: List[str] = sorted(
        (s for s in (secrets or []) if s),
        key=len,
        reverse=True,
    )
    for s in literals:
        if len(s) >= 4:  # avoid nukes from trivially short substrings
            out = out.replace(s, "***")

    out = _FIRMS_KEY_PATH.sub(r"\1***/", out)
    out = _CRED_IN_URL.sub(r"\1***@", out)
    return out


def safe_error(exc: BaseException, secrets: Optional[Iterable[str]] = None) -> str:
    """Build a redacted, still-informative message from an exception.

    Keeps the exception class name (useful: ConnectionError vs TimeoutError vs
    SSLError) but strips any secret material from the message text.
    """
    return f"{type(exc).__name__}: {redact_secrets(str(exc), secrets)}"
