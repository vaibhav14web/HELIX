import os
import sys
import ctypes
import logging

logger = logging.getLogger("helix.crypto")

_HEADER = b"HLXENCv1"

if sys.platform == "win32":
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ('cbData', wintypes.DWORD),
            ('pbData', ctypes.POINTER(ctypes.c_byte))
        ]

    def _win32_protect(data: bytes) -> bytes:
        if not data:
            return b""
        buffer = ctypes.create_string_buffer(data)
        data_in = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        data_out = DATA_BLOB()
        if ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(data_in), "HELIX_DPAPI", None, None, None, 0, ctypes.byref(data_out)
        ):
            encrypted = ctypes.string_at(data_out.pbData, data_out.cbData)
            ctypes.windll.kernel32.LocalFree(data_out.pbData)
            return encrypted
        raise RuntimeError("CryptProtectData failed")

    def _win32_unprotect(data: bytes) -> bytes:
        if not data:
            return b""
        buffer = ctypes.create_string_buffer(data)
        data_in = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        data_out = DATA_BLOB()
        if ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(data_in), None, None, None, None, 0, ctypes.byref(data_out)
        ):
            decrypted = ctypes.string_at(data_out.pbData, data_out.cbData)
            ctypes.windll.kernel32.LocalFree(data_out.pbData)
            return decrypted
        raise RuntimeError("CryptUnprotectData failed")

else:
    def _win32_protect(data: bytes) -> bytes:
        return data

    def _win32_unprotect(data: bytes) -> bytes:
        return data


def encrypt_bytes(data: bytes) -> bytes:
    """Encrypt raw bytes using Windows DPAPI and prepend HLXENCv1 header."""
    if not data:
        return _HEADER
    encrypted = _win32_protect(data)
    return _HEADER + encrypted


def decrypt_bytes(data: bytes) -> bytes:
    """Decrypt binary data. If HLXENCv1 header is present, decrypt payload; otherwise return raw data (legacy compatibility)."""
    if not data:
        return b""
    if data.startswith(_HEADER):
        payload = data[len(_HEADER):]
        if not payload:
            return b""
        return _win32_unprotect(payload)
    return data


def encrypt_string(text: str) -> bytes:
    return encrypt_bytes(text.encode("utf-8"))


def decrypt_string(data: bytes) -> str:
    raw = decrypt_bytes(data)
    return raw.decode("utf-8")
