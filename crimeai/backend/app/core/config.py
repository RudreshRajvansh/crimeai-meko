"""Typed application settings loaded from the environment."""
from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_DEV_SECRET = "dev-only-insecure-secret-change-me-0123456789abcdef"  # noqa: S105 - rejected outside dev/test


def _parse_csv(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


# The `| str` member makes pydantic-settings fall back to the raw string when the value is not JSON,
# so plain comma-separated env values reach _parse_csv instead of failing JSON decoding.
CsvList = Annotated[list[str] | str, BeforeValidator(_parse_csv)]


_PUBLIC_ROUTING_HOSTS = ("routing.openstreetmap.de", "router.project-osrm.org")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    APP_ENV: Literal["development", "staging", "production", "test"] = "development"
    APP_DEBUG: bool = False
    APP_SECRET_KEY: str = _INSECURE_DEV_SECRET
    APP_VERSION: str = "2.0.0"
    APP_NAME: str = "CrimeAI"
    APP_TIMEZONE: str = "Asia/Kolkata"
    ALLOWED_ORIGINS: CsvList = ["http://localhost:5173", "http://localhost:3000"]
    ALLOWED_HOSTS: CsvList = ["*"]

    API_V1_PREFIX: str = "/api/v1"
    DOCS_ENABLED: bool = True
    METRICS_ENABLED: bool = True
    METRICS_TOKEN: str = ""

    # YugabyteDB YSQL (PostgreSQL wire protocol, default port 5433).
    DATABASE_URL: str = "postgresql+asyncpg://crimeai:crimeai_dev_password@localhost:5433/crimeai"
    DATABASE_URL_SYNC: str = "postgresql://crimeai:crimeai_dev_password@localhost:5433/crimeai"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_STATEMENT_CACHE_SIZE: int = 100

    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_TTL: int = 300
    REDIS_MAX_CONNECTIONS: int = 100

    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    JWT_SECRET_KEY: str = _INSECURE_DEV_SECRET
    JWT_ALGORITHM: Literal["HS256", "HS384", "HS512"] = "HS256"
    JWT_ISSUER: str = "crimeai"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    WS_TICKET_TTL_SECONDS: int = 30
    AUTH_STATE_CACHE_TTL: int = 60

    REFRESH_COOKIE_NAME: str = "crimeai_refresh"
    REFRESH_COOKIE_SECURE: bool = True
    REFRESH_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "none"
    REFRESH_COOKIE_DOMAIN: str | None = None

    ALLOW_SELF_REGISTRATION: bool = False

    RATE_LIMIT_DEFAULT: str = "300/minute"
    RATE_LIMIT_AUTH: str = "10/minute"
    RATE_LIMIT_ML: str = "20/minute"
    FORWARDED_ALLOW_IPS: str = "127.0.0.1"

    STORAGE_BACKEND: Literal["local", "supabase", "s3"] = "local"
    LOCAL_STORAGE_DIR: str = "var/uploads"
    MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_STORAGE_BUCKET: str = "fir-documents"
    # S3-compatible object storage: DigitalOcean Spaces (https://blr1.digitaloceanspaces.com, region blr1) or Vultr
    # Object Storage (https://blr1.vultrobjects.com, region blr1).
    S3_ENDPOINT: str = ""
    S3_REGION: str = ""
    S3_BUCKET: str = ""
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""

    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = Field(0.1, ge=0.0, le=1.0)

    SPACY_MODEL: str = "en_core_web_sm"
    ENABLE_ZERO_SHOT: bool = False
    EMBEDDING_MODEL: str = "intfloat/multilingual-e5-small"
    EMBEDDING_DIM: int = 384
    DBSCAN_EPS: float = 0.5
    DBSCAN_MIN_SAMPLES: int = 3
    RISK_SCORE_SCALE: float = 6.0
    RISK_LOOKBACK_DAYS: int = 90
    HOTSPOT_MIN_TRAINING_ROWS: int = 200
    SERIES_RADIUS_KM: float = 3.0
    SERIES_WINDOW_DAYS: int = 21
    SERIES_MIN_SIMILARITY: float = 0.72
    SERIES_MIN_SIZE: int = 3
    # Keyed hash for phone/UPI/account identifiers in the link graph: linkable, never stored in clear.
    ENTITY_HASH_KEY: str = _INSECURE_DEV_SECRET
    LINK_ALERT_MIN_CASES: int = 2

    # Road routing for patrol plans (OSRM). Point at a self-hosted server for operational use.
    ROUTING_ENABLED: bool = True
    ROUTING_URL: str = "https://routing.openstreetmap.de"
    ROUTING_TIMEOUT_SECONDS: float = 8.0
    # Public OSRM servers receive patrol checkpoint coordinates; deployed environments must opt in explicitly.
    ROUTING_ALLOW_PUBLIC: bool = False

    # Gemini case briefs (English translation + summary of any FIR). Off until a key is set; only
    # PII-redacted text is sent. Model per https://ai.google.dev/gemini-api/docs/models.
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    # Reading handwriting needs the larger model: the lite one guesses at faint words.
    GEMINI_OCR_MODEL: str = "gemini-3.5-flash"
    # Vertex AI is the fallback when every Gemini API key fails; billed to this Google Cloud project.
    # On a Compute Engine VM the token comes from the metadata server; elsewhere set VERTEX_ACCESS_TOKEN.
    VERTEX_PROJECT: str = ""
    VERTEX_LOCATION: str = "global"
    VERTEX_ACCESS_TOKEN: str = ""
    # Off Google Cloud: a gcloud application-default credentials file (authorized_user), refreshed as needed.
    VERTEX_CREDENTIALS_FILE: str = ""
    GEMINI_TIMEOUT_SECONDS: float = 30.0

    # Meko shared memory between agencies (https://docs.mekodata.ai). Off until MEKO_API_KEY is set.
    MEKO_API_KEY: str = ""
    MEKO_MCP_URL: str = "https://mcp.mekodata.ai/mcp"
    MEKO_API_URL: str = "https://api.mekodata.ai/api/v1"
    MEKO_DATAPACK_PREFIX: str = "crimeai"
    # This deployment's agency on the grid. Agencies share MEKO_GRID_KEY so the same phone, UPI ID or account
    # fingerprints identically everywhere; the raw identifier never leaves the agency.
    MEKO_AGENCY_CODE: str = "DLP"
    MEKO_GRID_KEY: str = _INSECURE_DEV_SECRET
    MEKO_TIMEOUT_SECONDS: float = 90.0

    # Solana chain of custody: a case file's document and review hashes are sealed on chain as one Merkle root per
    # seal (Memo program). Devnet by default; on until the keypair file exists (scripts/solana_setup.py makes one).
    SOLANA_RPC_URL: str = "https://api.devnet.solana.com"
    SOLANA_CLUSTER: str = "devnet"
    SOLANA_KEYPAIR_FILE: str = "var/solana-devnet.json"

    # Tiger Cloud (TimescaleDB) mirror of the crime time series for the trend charts. Off until set.
    TIGER_DATABASE_URL: str = ""
    # Label of this deployment's rows, so several deployments can share one Tiger service.
    TIGER_DEPLOYMENT: str = "local"

    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: Literal["json", "console"] = "json"

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    @property
    def exposes_error_detail(self) -> bool:
        return self.APP_ENV in {"development", "test"}

    @property
    def meko_enabled(self) -> bool:
        return bool(self.MEKO_API_KEY)

    @property
    def tiger_enabled(self) -> bool:
        return bool(self.TIGER_DATABASE_URL)

    @property
    def solana_enabled(self) -> bool:
        return Path(self.SOLANA_KEYPAIR_FILE).is_file()

    @model_validator(mode="after")
    def _enforce_deployed_hardening(self) -> Settings:
        if self.APP_ENV not in {"production", "staging"}:
            return self
        problems: list[str] = []
        for name in ("APP_SECRET_KEY", "JWT_SECRET_KEY", "ENTITY_HASH_KEY"):
            value = getattr(self, name)
            if value == _INSECURE_DEV_SECRET or len(value) < 32:
                problems.append(f"{name} must be set to a random value of at least 32 characters")
        if self.meko_enabled and (self.MEKO_GRID_KEY == _INSECURE_DEV_SECRET or len(self.MEKO_GRID_KEY) < 32):
            problems.append("MEKO_GRID_KEY must be the random key shared by every agency on the grid (32+ characters)")
        if self.ALLOWED_HOSTS == ["*"]:
            problems.append("ALLOWED_HOSTS must list the public hostnames of the API")
        if any(origin == "*" for origin in self.ALLOWED_ORIGINS):
            problems.append("ALLOWED_ORIGINS cannot contain '*' when credentials are enabled")
        if self.STORAGE_BACKEND == "supabase" and not (self.SUPABASE_URL and self.SUPABASE_SERVICE_ROLE_KEY):
            problems.append("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for supabase storage")
        if self.STORAGE_BACKEND == "s3" and not all(
            (self.S3_ENDPOINT, self.S3_REGION, self.S3_BUCKET, self.S3_ACCESS_KEY, self.S3_SECRET_KEY)
        ):
            problems.append("S3_ENDPOINT, S3_REGION, S3_BUCKET, S3_ACCESS_KEY and S3_SECRET_KEY are required for s3 storage")
        if self.ROUTING_ENABLED and not self.ROUTING_ALLOW_PUBLIC and any(
            host in self.ROUTING_URL for host in _PUBLIC_ROUTING_HOSTS
        ):
            problems.append(
                "ROUTING_URL is a public OSRM server, so patrol checkpoint coordinates would leave the deployment: "
                "self-host OSRM, set ROUTING_ENABLED=false, or set ROUTING_ALLOW_PUBLIC=true to accept it"
            )
        if problems:
            raise ValueError("; ".join(problems))
        return self


settings = Settings()
