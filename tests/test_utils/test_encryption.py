"""Tests for utils/encryption.py."""

from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from utils.encryption import (
    ENCRYPTED_PREFIX,
    decrypt_api_key,
    encrypt_api_key,
    is_encrypted,
)


def test_encrypt_decrypt_roundtrip_with_dedicated_key() -> None:
    key = Fernet.generate_key()
    with patch("utils.encryption.get_settings") as gs:
        gs.return_value = MagicMock(encryption_key=key.decode(), jwt_secret="jwt-secret")
        encrypted = encrypt_api_key("my-secret-api-key")
        assert encrypted.startswith(ENCRYPTED_PREFIX)
        assert is_encrypted(encrypted)
        assert decrypt_api_key(encrypted) == "my-secret-api-key"


def test_encrypt_empty_raises() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        encrypt_api_key("")


def test_decrypt_empty_raises() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        decrypt_api_key("")


def test_decrypt_invalid_prefix() -> None:
    with pytest.raises(ValueError, match="Failed to decrypt API key"):
        decrypt_api_key("not-encrypted")


def test_decrypt_corrupted_data() -> None:
    key = Fernet.generate_key()
    with patch("utils.encryption.get_settings") as gs:
        gs.return_value = MagicMock(encryption_key=key.decode(), jwt_secret="jwt-secret")
        bad = f"{ENCRYPTED_PREFIX}not-valid-base64!!!"
        with pytest.raises(ValueError, match="Failed to decrypt"):
            decrypt_api_key(bad)


def test_encrypt_failure_raises_value_error() -> None:
    with patch("utils.encryption._get_fernet", side_effect=RuntimeError("fail")):
        with pytest.raises(ValueError, match="Failed to encrypt"):
            encrypt_api_key("key123456789")


def test_fallback_jwt_secret_derivation() -> None:
    with patch("utils.encryption.get_settings") as gs:
        gs.return_value = MagicMock(encryption_key=None, jwt_secret="test-jwt-secret-for-derivation")
        encrypted = encrypt_api_key("derived-key-test12")
        assert decrypt_api_key(encrypted) == "derived-key-test12"


def test_is_encrypted_false_for_empty() -> None:
    assert is_encrypted("") is False
    assert is_encrypted(None) is False  # type: ignore[arg-type]
