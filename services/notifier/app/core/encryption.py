"""Fernet encryption module for credential security.

Provides encrypt/decrypt/mask functions for sensitive notification
channel configuration fields (passwords, tokens, API keys, webhooks).

Key management:
  - Auto-generates Fernet key on first startup
  - Persists key to file (Docker volume for container restarts)
  - Gracefully degrades if key unavailable (logs warning, passes plaintext)
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("encryption")

# Module-level Fernet instance, initialized on startup
_fernet: Optional[Fernet] = None

# Sensitive field names across all channel types — blanket approach
SENSITIVE_FIELDS: set[str] = {
    "password",
    "token",
    "bot_token",
    "api_token",
    "webhook_url",
    "user_key",
    "sid",
    "api_key",
    "secret",
}


def init_encryption() -> None:
    """Initialize encryption by loading or generating a Fernet key.

    Loads key from settings.ENCRYPTION_KEY_PATH. If the file does not
    exist, generates a new key and writes it. If the directory for the
    key file does not exist, creates it.

    This must be called before any encrypt/decrypt operations.
    """
    global _fernet

    key_path = Path(settings.ENCRYPTION_KEY_PATH)

    if key_path.exists():
        try:
            key = key_path.read_bytes().strip()
            _fernet = Fernet(key)
            logger.info("Loaded encryption key from %s", key_path)
            return
        except Exception as e:
            logger.error("Failed to load encryption key from %s: %s", key_path, e)
            _fernet = None
            return

    # Key file does not exist
    # Check if this might be a restart where the key was expected
    if os.environ.get("ENCRYPTION_KEY_PATH"):
        logger.warning(
            "Encryption key file not found at %s. "
            "Channels with encrypted credentials will need to be re-configured.",
            key_path,
        )

    # Generate new key
    try:
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        key_path.write_bytes(key)
        # Restrict permissions to owner only
        key_path.chmod(0o600)
        _fernet = Fernet(key)
        logger.info("Generated new encryption key at %s", key_path)
    except Exception as e:
        logger.error("Failed to generate encryption key: %s", e)
        _fernet = None


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string using Fernet.

    Args:
        plaintext: The value to encrypt.

    Returns:
        Base64-encoded ciphertext string, or the plaintext unchanged
        if encryption is not available.
    """
    if not plaintext:
        return ""

    if _fernet is None:
        logger.warning("Encryption not initialized — returning plaintext unchanged")
        return plaintext

    try:
        return _fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")
    except Exception as e:
        logger.error("Encryption failed: %s", e)
        return plaintext


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a Fernet ciphertext string.

    Args:
        ciphertext: Base64-encoded Fernet ciphertext.

    Returns:
        Decrypted plaintext string, or empty string if decryption fails
        (e.g., data was encrypted with a different key).
    """
    if not ciphertext:
        return ""

    if _fernet is None:
        logger.warning("Encryption not initialized — cannot decrypt")
        return ""

    try:
        return _fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        logger.warning(
            "Decryption failed (InvalidToken) — data was encrypted with a different key"
        )
        return ""
    except Exception as e:
        logger.error("Decryption failed: %s", e)
        return ""


def mask_value(value: str) -> str:
    """Mask a sensitive value for display.

    Args:
        value: The sensitive value to mask.

    Returns:
        '********' for any non-empty value, empty string for empty/None.
    """
    if not value:
        return ""
    return "********"


def encrypt_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Encrypt sensitive fields in a configuration dictionary.

    Args:
        config: Channel configuration dict.

    Returns:
        New dict with sensitive fields encrypted; non-sensitive fields
        passed through unchanged.
    """
    result = {}
    for key, value in config.items():
        if key in SENSITIVE_FIELDS and isinstance(value, str) and value:
            result[key] = encrypt_value(value)
        else:
            result[key] = value
    return result


def decrypt_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Decrypt sensitive fields in a configuration dictionary.

    Args:
        config: Channel configuration dict with encrypted values.

    Returns:
        New dict with sensitive fields decrypted; non-sensitive fields
        passed through unchanged.
    """
    result = {}
    for key, value in config.items():
        if key in SENSITIVE_FIELDS and isinstance(value, str) and value:
            result[key] = decrypt_value(value)
        else:
            result[key] = value
    return result


def mask_config(config: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """Mask sensitive fields in a configuration dictionary.

    Args:
        config: Channel configuration dict.

    Returns:
        Tuple of (masked_config, has_credential). has_credential is True
        if any sensitive field had a non-empty value.
    """
    result = {}
    has_credential = False
    for key, value in config.items():
        if key in SENSITIVE_FIELDS:
            if isinstance(value, str) and value:
                has_credential = True
                result[key] = mask_value(value)
            else:
                result[key] = value
        else:
            result[key] = value
    return result, has_credential
