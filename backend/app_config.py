"""
AgriSmoke AI - Central Application Configuration
Single source of truth for all environment-driven runtime settings.

Every value here is safe by default for a public, read-only production
deployment (Render + Supabase/SQLite). Local development can relax these via
the project-root .env file. Nothing secret is stored in code; secrets come only
from the environment (Render dashboard / .env, which is git-ignored).
"""

import os
from pathlib import Path
from typing import List

ROOT_DIR = Path(__file__).resolve().parent.parent


def _get_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(key: str, default: int) -> int:
    try:
        return int(str(os.getenv(key, default)).strip())
    except (TypeError, ValueError):
        return default


class AppConfig:
    """Immutable snapshot of runtime configuration read from the environment."""

    def __init__(self) -> None:
        # deployment environment: "production" | "staging" | "development"
        self.environment: str = os.getenv("ENVIRONMENT", "development").strip().lower()

        # Server binding. Containers/PaaS MUST listen on 0.0.0.0, not 127.0.0.1.
        self.host: str = os.getenv("HOST", "0.0.0.0").strip() or "0.0.0.0"
        self.port: int = _get_int("PORT", 8000)

        # Reload / verbose dev behaviour only outside production.
        self.is_production: bool = self.environment in {"production", "prod"}
        self.reload_enabled: bool = _get_bool("RELOAD", not self.is_production)

        # Publicly reachable base URL of this app (used for CORS + HSTS preload).
        self.public_url: str = os.getenv("PUBLIC_URL", "").strip()

        # CORS: comma-separated explicit origins. We NEVER combine "*" with
        # credentials. If empty and not production, allow localhost dev origins.
        self.cors_origins: List[str] = self._resolve_cors_origins()

        # Interactive API docs (Swagger/ReDoc). Disabled by default in production
        # to avoid disclosing the full API surface publicly.
        self.docs_enabled: bool = _get_bool("DOCS_ENABLED", not self.is_production)

        # Read-only mode: block all state-changing endpoints (POST/PUT/PATCH/DELETE)
        # except the stateless compute path. On by default in production.
        self.read_only: bool = _get_bool("READ_ONLY", self.is_production)

        # Simple in-process rate limiting for expensive ML/report endpoints.
        self.rate_limit_enabled: bool = _get_bool("RATE_LIMIT_ENABLED", self.is_production)
        self.rate_limit_per_minute: int = _get_int("RATE_LIMIT_PER_MINUTE", 60)

        # SQLite database location. Overridable so PaaS can point it at a mounted
        # volume (e.g. /var/data/agri_smoke.db). When unset, uses the repo default.
        self.db_path: Path = self._resolve_db_path()

        # Optional Postgres/Supabase URL. Presence of this value is the signal that
        # the deployment intends the managed-DB upgrade path (documented, not yet
        # wired into the query layer). Kept here so config is forward-compatible.
        self.database_url: str = os.getenv("DATABASE_URL", "").strip()

        # Trust X-Forwarded-* headers from the Render/nginx reverse proxy.
        self.proxy_headers: bool = _get_bool("PROXY_HEADERS", True)
        self.forwarded_allow_ips: str = os.getenv("FORWARDED_ALLOW_IPS", "*")

        # Background jobs. Both default ON. A deployment MUST run a single app
        # instance / worker so scheduled jobs execute exactly once; if you ever
        # scale to more than one instance, set these to false on every instance
        # except a designated single "worker" service (otherwise each replica
        # would run its own ingestion + backup loop against the same disk).
        self.scheduler_enabled: bool = _get_bool("SCHEDULER_ENABLED", True)
        self.maintenance_enabled: bool = _get_bool("MAINTENANCE_ENABLED", True)

        # On-demand NASA FIRMS fetching for stateless/public deployments that run
        # NO background ingestion scheduler. When true, the fire hotspots and
        # district-count endpoints pull a LIVE FIRMS snapshot on the read path and
        # hold it in a short-lived, single-flight in-memory cache (never written to
        # the DB), so visitors see current satellite data without a persistent
        # store or a continuously-running job. Default OFF keeps the existing
        # scheduler-driven behavior untouched; bounded by TTL so free-tier outbound
        # traffic limits are respected. Requires NASA_FIRMS_MAP_KEY; without it the
        # endpoints transparently fall back to the seeded reference data.
        self.firms_on_demand: bool = _get_bool("FIRMS_ON_DEMAND", False)
        self.firms_on_demand_ttl: int = _get_int("FIRMS_ON_DEMAND_TTL_SECONDS", 900)

    def _resolve_cors_origins(self) -> List[str]:
        raw = os.getenv("CORS_ORIGINS", "").strip()
        if raw:
            return [o.strip() for o in raw.split(",") if o.strip()]
        if self.public_url:
            return [self.public_url.rstrip("/")]
        if self.is_production:
            # Production without an explicit origin: same-origin only (empty list).
            # The frontend is served by this same app, so no cross-origin needed.
            return []
        # Development conveniences for `python backend/run.py`.
        return [
            "http://127.0.0.1:8000",
            "http://localhost:8000",
            "http://127.0.0.1:5500",
            "http://localhost:5500",
        ]

    def _resolve_db_path(self) -> Path:
        override = os.getenv("DB_PATH", "").strip()
        if override:
            p = Path(override).expanduser()
            p.parent.mkdir(parents=True, exist_ok=True)
            return p
        return ROOT_DIR / "database" / "agri_smoke.db"

    def __repr__(self) -> str:
        return (
            f"<AppConfig env={self.environment} host={self.host}:{self.port} "
            f"docs={self.docs_enabled} read_only={self.read_only} "
            f"cors={self.cors_origins or 'same-origin'}>"
        )


# Global singleton
config = AppConfig()
