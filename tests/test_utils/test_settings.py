"""Tests for config/settings.py validators and helpers."""

import pytest
from pydantic import ValidationError

from config.settings import (
    DatabaseSettings,
    Settings,
    clear_settings_cache,
    get_database_settings,
    get_security_settings,
    get_settings,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_settings_cache()
    yield
    clear_settings_cache()


def test_database_url_converts_to_asyncpg() -> None:
    s = Settings(
        database_url="postgresql://user:pass@localhost/db",
        jwt_secret="a" * 32 + "Ab1!",
    )
    assert s.database_url.startswith("postgresql+asyncpg://")


def test_database_url_rejects_invalid_scheme() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="mysql://localhost/db", jwt_secret="a" * 32 + "Ab1!")


def test_jwt_secret_rejects_short() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql://localhost/db", jwt_secret="short")


def test_jwt_secret_rejects_weak_pattern() -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql://localhost/db",
            jwt_secret="password" * 4,
        )


def test_jwt_secret_rejects_low_entropy() -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql://localhost/db",
            jwt_secret="a" * 40,
        )


def test_encryption_key_validates_fernet() -> None:
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    s = Settings(
        database_url="postgresql://localhost/db",
        jwt_secret="a" * 32 + "Ab1!",
        encryption_key=key,
    )
    assert s.encryption_key == key


def test_encryption_key_rejects_invalid() -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql://localhost/db",
            jwt_secret="a" * 32 + "Ab1!",
            encryption_key="not-a-fernet-key",
        )


def test_gemini_api_key_rejects_invalid() -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql://localhost/db",
            jwt_secret="a" * 32 + "Ab1!",
            gemini_api_key="bad key with spaces",
        )


def test_cors_origins_list_input() -> None:
    s = Settings(
        database_url="postgresql://localhost/db",
        jwt_secret="a" * 32 + "Ab1!",
        cors_origins=["http://localhost:3000"],
    )
    assert s.cors_origins == ["http://localhost:3000"]


def test_cors_origins_empty_string() -> None:
    s = Settings(
        database_url="postgresql://localhost/db",
        jwt_secret="a" * 32 + "Ab1!",
        cors_origins="   ",
    )
    assert s.cors_origins == []


def test_cors_origins_rejects_invalid_scheme() -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql://localhost/db",
            jwt_secret="a" * 32 + "Ab1!",
            cors_origins="ftp://evil.com",
        )


def test_allowed_hosts_list_input() -> None:
    s = Settings(
        database_url="postgresql://localhost/db",
        jwt_secret="a" * 32 + "Ab1!",
        allowed_hosts=["example.com"],
    )
    assert s.allowed_hosts == ["example.com"]


def test_allowed_hosts_empty_defaults_localhost() -> None:
    s = Settings(
        database_url="postgresql://localhost/db",
        jwt_secret="a" * 32 + "Ab1!",
        allowed_hosts="",
    )
    assert "localhost" in s.allowed_hosts


def test_base_url_rejects_http_in_production_host() -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql://localhost/db",
            jwt_secret="a" * 32 + "Ab1!",
            base_url="http://applypilot.example.com",
        )


def test_is_production_property() -> None:
    s = Settings(
        database_url="postgresql://localhost/db",
        jwt_secret="a" * 32 + "Ab1!",
        debug=False,
        testing=False,
    )
    assert s.is_production is True
    assert s.session_cookie_secure_production is True


def test_is_google_oauth_configured() -> None:
    s = Settings(
        database_url="postgresql://localhost/db",
        jwt_secret="a" * 32 + "Ab1!",
        google_client_id="id",
        google_client_secret="secret",
    )
    assert s.is_google_oauth_configured is True


def test_database_settings_urls() -> None:
    s = Settings(
        database_url="postgresql://user:pass@localhost/db",
        jwt_secret="a" * 32 + "Ab1!",
    )
    db = DatabaseSettings(s)
    assert db.async_database_url.startswith("postgresql+asyncpg://")
    assert "+asyncpg" not in db.sync_database_url
    assert db.connection_pool_params["pool_size"] == 5


def test_database_url_empty_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="", jwt_secret="a" * 32 + "Ab1!")


def test_jwt_secret_empty_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql://localhost/db", jwt_secret="")


def test_encryption_key_none_allowed() -> None:
    s = Settings(
        database_url="postgresql://localhost/db",
        jwt_secret="a" * 32 + "Ab1!",
        encryption_key=None,
    )
    assert s.encryption_key is None


def test_gemini_api_key_none_allowed() -> None:
    s = Settings(
        database_url="postgresql://localhost/db",
        jwt_secret="a" * 32 + "Ab1!",
        gemini_api_key=None,
    )
    assert s.gemini_api_key is None


def test_gemini_api_key_valid_passes() -> None:
    s = Settings(
        database_url="postgresql://localhost/db",
        jwt_secret="a" * 32 + "Ab1!",
        gemini_api_key="AIzaSyD" + "a" * 30,
    )
    assert s.gemini_api_key.startswith("AIza")


def test_database_settings_asyncpg_url_passthrough() -> None:
    s = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost/db",
        jwt_secret="a" * 32 + "Ab1!",
    )
    db = DatabaseSettings(s)
    assert db.async_database_url.startswith("postgresql+asyncpg://")


def test_get_settings_cached() -> None:
    a = get_settings()
    b = get_settings()
    assert a is b


def test_get_security_settings() -> None:
    sec = get_security_settings()
    assert "secret_key" in sec.jwt_config


def test_get_database_settings() -> None:
    db = get_database_settings()
    assert db.async_database_url.startswith("postgresql")


def test_database_settings_rewrites_postgresql_scheme() -> None:
    class _SettingsStub:
        database_url = "postgresql://user:pass@localhost:5432/applypilot"

    db = DatabaseSettings(_SettingsStub())
    assert db.async_database_url == "postgresql+asyncpg://user:pass@localhost:5432/applypilot"


def test_use_cloud_tasks_property() -> None:
    s = Settings(
        database_url="postgresql://localhost/db",
        jwt_secret="a" * 32 + "Ab1!",
        cloud_tasks_service_url="https://svc.run.app",
        cloud_tasks_service_account="sa@proj.iam.gserviceaccount.com",
        cloud_tasks_secret="secret",
    )
    assert s.use_cloud_tasks is True
    s2 = Settings(
        database_url="postgresql://localhost/db",
        jwt_secret="a" * 32 + "Ab1!",
    )
    assert s2.use_cloud_tasks is False
