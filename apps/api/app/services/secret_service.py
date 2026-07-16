import os
from cryptography.fernet import Fernet
from app.config import settings


def _load_or_create_key() -> bytes:
    key_path = settings.secret_key_path
    if key_path.exists():
        return key_path.read_bytes()

    key = Fernet.generate_key()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(key)
    if os.name != "nt":
        os.chmod(key_path, 0o600)
    return key


def _get_fernet() -> Fernet:
    return Fernet(_load_or_create_key())


def encrypt_api_key(api_key: str) -> str | None:
    if not api_key:
        return None
    fernet = _get_fernet()
    return fernet.encrypt(api_key.encode()).decode()


def decrypt_api_key(encrypted: str | None) -> str | None:
    if not encrypted:
        return None
    fernet = _get_fernet()
    return fernet.decrypt(encrypted.encode()).decode()
