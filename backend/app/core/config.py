"""Centralised, environment-driven configuration for OpsGPT.

Everything tunable lives here and is overridable via environment variables /
the .env file. No secrets or hostnames are hard-coded anywhere else.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Insecure placeholder shipped in the example config / compose fallback. The app
# refuses to start in production if the real secret still equals this.
_INSECURE_JWT_DEFAULT = "CHANGE_ME_IN_PRODUCTION_use_a_long_random_string"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPSGPT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- application ---
    app_name: str = "OpsGPT"
    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    api_prefix: str = "/api"

    # --- CORS ---
    # Stored as a comma-separated string so a plain env value parses cleanly
    # (pydantic-settings would otherwise try to JSON-decode a list-typed env).
    # Use `cors_origin_list` for the parsed value.
    cors_origins: str = "http://localhost:5173,http://localhost"

    # --- upstream llama.cpp servers (OpenAI-compatible) ---
    # Qwen3 (chat/docs/tools), plus Phase 5 specialist servers.
    llamacpp_base_url: str = "http://llamacpp:8080"
    model_phi_base_url: str = "http://phi:8080"
    model_xcoder_base_url: str = "http://xcoder:8080"
    request_timeout_s: float = 600.0
    connect_timeout_s: float = 10.0

    # --- generation defaults ---
    default_temperature: float = 0.7
    default_top_p: float = 0.95
    default_max_tokens: int = 1024

    # --- database (Phase 2) ---
    database_url: str = "postgresql+asyncpg://opsgpt:opsgpt@postgres:5432/opsgpt"

    # --- Redis (Phase 3): rate limiting + caching ---
    redis_url: str = "redis://redis:6379/0"
    rate_limit_per_min: int = 30  # per user; 0 disables. Admins are exempt.
    embed_cache_ttl_s: int = 3600  # cache query embeddings (RAG) for this long

    # --- auth abuse protection (login/register) ---
    auth_ip_rate_per_min: int = 10     # login+register attempts per client IP / min
    login_max_failures: int = 5        # consecutive failures before lockout
    login_lockout_min: int = 15        # lockout window (minutes) once tripped

    # --- SSRF guard for admin-configured provider URLs (GitLab/Elasticsearch) ---
    # Internal/private ranges ARE allowed (the whole point is scanning internal
    # infra); only loopback + link-local/cloud-metadata are blocked by default.
    mcp_block_link_local: bool = True

    # --- tools / agentic (Kubernetes MCP-style) ---
    tools_kubernetes_enabled: bool = True
    tools_kubeconfig: str = "/secrets/kube-readonly.yaml"
    # rounds + token budget for a single tool-using turn
    tools_max_tokens: int = 1024

    # --- Elasticsearch MCP provider (read-only) ---
    # Provider is registered only when es_url is set.
    es_url: str = ""
    es_username: str = ""
    es_password: str = ""
    es_api_key: str = ""  # base64 "id:key" form (Authorization: ApiKey ...)
    es_verify_tls: bool = True

    # --- Weekly AI digest (delivery & reliability summary -> email) ---
    digest_enabled: bool = False       # send the weekly digest automatically
    digest_day: int = 0                # 0=Monday … 6=Sunday (local time, UTC+8)
    digest_hour: int = 9               # local hour to send
    digest_to: str = ""                # comma-separated recipient addresses
    # SMTP (defaults target Outlook / Microsoft 365). Use an app password if the
    # mailbox has MFA; basic SMTP AUTH must be enabled for the tenant.
    smtp_host: str = "smtp.office365.com"
    smtp_port: int = 587
    smtp_user: str = ""                # sending mailbox; also default From
    smtp_password: str = ""            # app password recommended
    smtp_from: str = ""                # overrides From; defaults to smtp_user
    smtp_starttls: bool = True

    # --- Live failure alerts (newly failed GitLab pipelines / K8s pods) ---
    alerts_enabled: bool = True        # run the background monitor
    alerts_interval_s: int = 120       # how often to check for new failures
    alerts_max_per_cycle: int = 6      # cap AI analyses per cycle (rest next cycle)
    alerts_email: bool = False         # also email each new alert
    alerts_to: str = ""                # recipients for alert emails; falls back to digest_to

    # --- RAG / document chat ---
    embed_base_url: str = "http://embed:8080"
    # RAG now uses BGE-large-en-v1.5 (1024-dim); this is the doc_chunks vector width.
    embed_dim: int = 1024
    # Optional second embedding model: BGE-large-en-v1.5 (1024-dim). Registered
    # only when set; exposed via /v1/embeddings with model="bge".
    embed_bge_base_url: str = ""
    embed_bge_dim: int = 1024
    # Cross-encoder reranker (bge-reranker-v2-m3). When set, RAG retrieves
    # `rag_rerank_candidates` by embedding, then reranks down to `rag_top_k`.
    reranker_base_url: str = ""
    rag_rerank_candidates: int = 20
    upload_dir: str = "/uploads"
    max_upload_mb: int = 25
    # kept under BGE's 512-token limit (~1.7 chars/token) so chunks embed without truncation
    chunk_chars: int = 800
    chunk_overlap: int = 150
    rag_top_k: int = 5

    # --- auth / JWT (Phase 2) ---
    # jwt_secret MUST be overridden in production (set OPSGPT_JWT_SECRET).
    jwt_secret: str = "CHANGE_ME_IN_PRODUCTION_use_a_long_random_string"
    jwt_algorithm: str = "HS256"
    access_token_ttl_min: int = 30
    refresh_token_ttl_days: int = 7
    api_key_prefix: str = "opsk_"
    # Token endpoint (POST /auth/token) for gateway clients that authenticate with
    # username+password and cache the returned bearer. Long TTL because it's cached.
    token_endpoint_ttl_min: int = 525600  # 365 days

    # --- auth cookies (web UI). Tokens live in httpOnly cookies, not JS storage,
    # so they cannot be exfiltrated by XSS. API keys still use the Bearer header. ---
    access_cookie_name: str = "opsgpt_access"
    refresh_cookie_name: str = "opsgpt_refresh"
    cookie_secure: bool = True       # only sent over HTTPS (prod is behind a TLS edge)
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    # First-run admin seed: if set and the users table is empty, this admin is
    # created on startup. Override via OPSGPT_ADMIN_EMAIL / OPSGPT_ADMIN_PASSWORD.
    admin_email: str = "admin@opsgpt.local"
    admin_password: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _enforce_production_secrets(self) -> "Settings":
        """Fail fast in production rather than silently running insecure.

        Only enforced when environment == 'production' so local/dev runs with the
        convenience defaults still work.
        """
        if self.environment != "production":
            return self
        problems: list[str] = []
        if not self.jwt_secret or self.jwt_secret == _INSECURE_JWT_DEFAULT:
            problems.append("OPSGPT_JWT_SECRET is unset or the insecure default")
        if len(self.jwt_secret) < 32:
            problems.append("OPSGPT_JWT_SECRET must be at least 32 chars")
        if not self.admin_password and "postgresql" in self.database_url:
            # admin seeding is skipped without a password; warn loudly via error
            problems.append("OPSGPT_ADMIN_PASSWORD is unset (no admin can be seeded)")
        if problems:
            raise ValueError(
                "Refusing to start in production with insecure config: "
                + "; ".join(problems)
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton accessor so settings are parsed exactly once per process."""
    return Settings()
