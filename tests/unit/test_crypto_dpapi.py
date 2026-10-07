import pytest
from foundation.storage_manager.crypto import (
    encrypt_bytes,
    decrypt_bytes,
    encrypt_string,
    decrypt_string,
    _HEADER,
)


def test_dpapi_bytes_roundtrip():
    data = b"secret conversation payload 12345"
    encrypted = encrypt_bytes(data)
    assert encrypted.startswith(_HEADER)
    assert encrypted != data
    decrypted = decrypt_bytes(encrypted)
    assert decrypted == data


def test_dpapi_string_roundtrip():
    text = "User preferences JSON string: {'theme': 'dark'}"
    encrypted = encrypt_string(text)
    assert encrypted.startswith(_HEADER)
    decrypted = decrypt_string(encrypted)
    assert decrypted == text


def test_legacy_plaintext_fallback():
    plaintext = b"legacy json line text"
    decrypted = decrypt_bytes(plaintext)
    assert decrypted == plaintext


def test_empty_payload_handling():
    assert decrypt_bytes(b"") == b""
    assert decrypt_string(_HEADER) == ""
