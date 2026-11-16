"""Application configuration and auto-persisted cryptographic secrets."""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.services.common import b64url_nopad


def generate_vapid_keypair() -> tuple[str, str]:
    """Generate a P-256 ECDSA VAPID keypair in unpadded base64url format."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    priv_bytes = private_key.private_numbers().private_value.to_bytes(32, "big")
    pub_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    return b64url_nopad(pub_bytes), b64url_nopad(priv_bytes)


class Settings(BaseSettings):
    """Runtime settings sourced from environment variables and persisted defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_domain: str = "sniper.hodgman.net"
    app_origin: str = "https://sniper.hodgman.net"
    host_bind: str = "127.0.0.1"
    host_port: int = 8000

    data_dir: Path = Field(default=Path("/app/data"))
    static_dir: Path = Field(default=Path("/app/static"))

    admin_username: str = ""
    admin_password: str = ""

    session_secret: str = ""
    session_cookie_name: str = "cs_session"
    session_ttl_seconds: int = 60 * 60 * 24 * 30

    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = ""

    discord_shared_webhook_url: str = ""

    poll_max_rps: float = 0.9
    cornell_api_timeout_sec: float = 8.0
    cornell_base_url: str = "https://classes.cornell.edu/api/2.0"
    catalog_sync_interval_hours: float = 12.0
    max_subjects_per_invited_user: int = 8
    allow_custom_personal_webhooks: bool = True

    enable_background_workers: bool = True

    @property
    def db_path(self) -> Path:
        return self.data_dir / "classsniper.db"

    @property
    def effective_vapid_subject(self) -> str:
        if self.vapid_subject.strip():
            return self.vapid_subject.strip()
        return f"mailto:admin@{self.app_domain}"

    @property
    def cookie_secure(self) -> bool:
        return self.app_origin.lower().startswith("https://")

    def ensure_persisted_secrets(self) -> None:
        """Create data_dir and generate missing session/VAPID secrets on first run."""
        self.data_dir.mkdir(parents=True, exist_ok=True)

        if not self.session_secret.strip():
            secret_file = self.data_dir / "session_secret.txt"
            if secret_file.exists():
                self.session_secret = secret_file.read_text(encoding="utf-8").strip()
            else:
                self.session_secret = secrets.token_urlsafe(48)
                secret_file.write_text(self.session_secret, encoding="utf-8")
                os.chmod(secret_file, 0o600)

        if not (self.vapid_public_key.strip() and self.vapid_private_key.strip()):
            vapid_file = self.data_dir / "vapid_keys.json"
            if vapid_file.exists():
                stored = json.loads(vapid_file.read_text(encoding="utf-8"))
                self.vapid_public_key = stored["public_key"]
                self.vapid_private_key = stored["private_key"]
            else:
                pub, priv = generate_vapid_keypair()
                self.vapid_public_key = pub
                self.vapid_private_key = priv
                vapid_file.write_text(
                    json.dumps({"public_key": pub, "private_key": priv}, indent=2),
                    encoding="utf-8",
                )
                os.chmod(vapid_file, 0o600)


_settings_singleton: Optional[Settings] = None


def get_settings() -> Settings:
    """Return initialized singleton Settings instance."""
    global _settings_singleton
    if _settings_singleton is None:
        settings = Settings()
        settings.ensure_persisted_secrets()
        _settings_singleton = settings
    return _settings_singleton
