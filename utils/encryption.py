"""
Encryption utilities for secure storage of sensitive data like API keys.

Key selection priority:
1. ENCRYPTION_KEY env var — a dedicated Fernet key that can be rotated independently
   of the JWT secret.  Generate with:
       python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
2. JWT_SECRET — derived via SHA-256 for backward compatibility when no dedicated key
   is configured.  Not recommended for production because rotating the JWT secret
   would break decryption of stored API keys.
"""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from config.settings import get_settings
from utils.logging_config import sanitize_log_value

logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTS
# =============================================================================

# Prefix to identify encrypted values
ENCRYPTED_PREFIX: str = "enc:v1:"


# =============================================================================
# KEY DERIVATION
# =============================================================================


def _get_encryption_key() -> bytes:
    """
    Return a Fernet-compatible encryption key.

    Prefers the dedicated ENCRYPTION_KEY setting.  Falls back to deriving a key
    from JWT_SECRET via SHA-256 for backward compatibility.

    Returns:
        bytes: A base64url-encoded 32-byte key suitable for Fernet
    """
    settings = get_settings()

    if settings.encryption_key:
        # Use the dedicated key directly — it must already be a valid Fernet key
        # (base64url-encoded 32-byte value).
        return settings.encryption_key.encode()

    # Backward-compat fallback: derive from JWT secret
    logger.warning(
        "ENCRYPTION_KEY is not set; deriving encryption key from JWT_SECRET. "
        "Set a dedicated ENCRYPTION_KEY to allow safe JWT secret rotation."
    )
    key_bytes = hashlib.sha256(settings.jwt_secret.encode()).digest()
    return base64.urlsafe_b64encode(key_bytes)


def _get_fernet() -> Fernet:
    """
    Get a Fernet instance for encryption/decryption.
    
    Returns:
        Fernet: Configured Fernet instance
    """
    return Fernet(_get_encryption_key())


# =============================================================================
# ENCRYPTION/DECRYPTION FUNCTIONS
# =============================================================================


def encrypt_api_key(api_key: str) -> str:
    """
    Encrypt an API key for secure storage.
    
    Args:
        api_key: The plaintext API key to encrypt
        
    Returns:
        str: Encrypted API key with version prefix
        
    Raises:
        ValueError: If api_key is empty or None
    """
    if not api_key or not api_key.strip():
        raise ValueError("API key cannot be empty")
    
    try:
        fernet = _get_fernet()
        encrypted_bytes = fernet.encrypt(api_key.encode())
        encrypted_str = base64.urlsafe_b64encode(encrypted_bytes).decode()
        
        # Add prefix for version identification
        return f"{ENCRYPTED_PREFIX}{encrypted_str}"
        
    except Exception as e:
        logger.error('Failed to encrypt API key: %s', sanitize_log_value(e), exc_info=True)
        raise ValueError("Failed to encrypt API key")


def decrypt_api_key(encrypted_key: str) -> str:
    """
    Decrypt an encrypted API key.
    
    Args:
        encrypted_key: The encrypted API key (with version prefix)
        
    Returns:
        str: The decrypted plaintext API key
        
    Raises:
        ValueError: If decryption fails or key format is invalid
    """
    if not encrypted_key:
        raise ValueError("Encrypted key cannot be empty")
    
    try:
        # Remove version prefix
        if encrypted_key.startswith(ENCRYPTED_PREFIX):
            encrypted_data = encrypted_key[len(ENCRYPTED_PREFIX):]
        else:
            raise ValueError("Invalid encrypted key format")
        
        # Decode and decrypt
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_data)
        fernet = _get_fernet()
        decrypted_bytes = fernet.decrypt(encrypted_bytes)
        
        return decrypted_bytes.decode()
        
    except InvalidToken:
        logger.warning("Failed to decrypt API key: invalid token")
        raise ValueError("Failed to decrypt API key: invalid or corrupted data")
    except Exception as e:
        logger.error('Failed to decrypt API key: %s', sanitize_log_value(e), exc_info=True)
        raise ValueError("Failed to decrypt API key")


def is_encrypted(value: str) -> bool:
    """
    Check if a value appears to be encrypted.
    
    Args:
        value: The value to check
        
    Returns:
        bool: True if the value has the encryption prefix
    """
    return value.startswith(ENCRYPTED_PREFIX) if value else False

