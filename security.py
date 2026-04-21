import os
import re
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken


_ENC_PREFIX = "enc:v1:"


def _get_fernet() -> Fernet:
    key = os.getenv("PHONE_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "Missing PHONE_ENCRYPTION_KEY. Generate one with:\n"
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode("utf-8") if isinstance(key, str) else key)

def encryption_is_configured() -> bool:
    return bool(os.getenv("PHONE_ENCRYPTION_KEY"))


def normalize_phone(phone_number: str) -> str:
    clean = re.sub(r"\D+", "", phone_number or "")
    if len(clean) == 8:
        clean = "371" + clean
    return clean


def last4_from_phone(phone_number: str) -> Optional[str]:
    clean = normalize_phone(phone_number)
    return clean[-4:] if clean else None


def mask_last4(last4: Optional[str]) -> str:
    if not last4:
        return ""
    return f"****{last4}"


def encrypt_phone(plain_phone_number: str) -> str:
    f = _get_fernet()
    token = f.encrypt(plain_phone_number.encode("utf-8")).decode("utf-8")
    return f"{_ENC_PREFIX}{token}"


def decrypt_phone(encrypted_phone_number: str) -> str:
    if not encrypted_phone_number:
        return ""
    if not encrypted_phone_number.startswith(_ENC_PREFIX):
        # legacy plaintext in DB
        return encrypted_phone_number
    token = encrypted_phone_number[len(_ENC_PREFIX) :]
    f = _get_fernet()
    try:
        return f.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as e:
        raise RuntimeError("Invalid PHONE_ENCRYPTION_KEY or corrupted encrypted phone value") from e
