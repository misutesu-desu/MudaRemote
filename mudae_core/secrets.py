"""Credential storage with Windows DPAPI and cross-platform keyring support."""

import base64
import ctypes
import os
import re
from ctypes import wintypes

from .config import atomic_write_json, load_json


class SecretStoreError(RuntimeError):
    pass


class SecretStore:
    SERVICE = "MudaRemote"

    def __init__(self, base_path):
        self.path = os.path.join(base_path, ".mudae-secrets.json")

    @staticmethod
    def _env_name(preset_name):
        clean = re.sub(r"[^A-Za-z0-9]+", "_", preset_name).strip("_").upper()
        return "MUDAREMOTE_TOKEN_{}".format(clean)

    def get_token(self, preset_name, legacy_token=""):
        env_token = os.environ.get(self._env_name(preset_name))
        if env_token:
            return env_token
        try:
            stored = self._get_platform_secret(preset_name)
            if stored:
                return stored
        except SecretStoreError:
            pass
        return str(legacy_token or "")

    def set_token(self, preset_name, token):
        token = str(token or "")
        if token and os.environ.get(self._env_name(preset_name)) == token:
            return
        if os.name == "nt":
            self._set_dpapi_secret(preset_name, token)
            return
        try:
            import keyring
            if token:
                keyring.set_password(self.SERVICE, preset_name, token)
            else:
                try:
                    keyring.delete_password(self.SERVICE, preset_name)
                except keyring.errors.PasswordDeleteError:
                    pass
        except Exception as exc:
            raise SecretStoreError(
                "Secure token storage is unavailable. Install/configure the 'keyring' package or use {}."
                .format(self._env_name(preset_name))
            ) from exc

    def delete_token(self, preset_name):
        self.set_token(preset_name, "")

    def _get_platform_secret(self, preset_name):
        if os.name == "nt":
            values = self._load_dpapi_values()
            encoded = values.get(preset_name)
            return self._dpapi_unprotect(encoded) if encoded else ""
        try:
            import keyring
            return keyring.get_password(self.SERVICE, preset_name) or ""
        except Exception as exc:
            raise SecretStoreError(str(exc)) from exc

    def _set_dpapi_secret(self, preset_name, token):
        values = self._load_dpapi_values()
        if token:
            values[preset_name] = self._dpapi_protect(token)
        else:
            values.pop(preset_name, None)
        atomic_write_json(self.path, values)

    def _load_dpapi_values(self):
        try:
            values = load_json(self.path, {})
            if not isinstance(values, dict):
                raise ValueError("secret store root is not an object")
            return values
        except Exception as exc:
            raise SecretStoreError("The encrypted token store is unreadable; restore or remove {}.".format(self.path)) from exc

    @staticmethod
    def _blob(data):
        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]
        buffer = ctypes.create_string_buffer(data)
        return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer, DATA_BLOB

    @classmethod
    def _dpapi_protect(cls, value):
        raw = value.encode("utf-8")
        in_blob, in_buffer, blob_type = cls._blob(raw)
        out_blob = blob_type()
        if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(in_blob), cls.SERVICE, None, None, None, 0, ctypes.byref(out_blob)
        ):
            raise SecretStoreError("Windows DPAPI could not encrypt the token.")
        try:
            encrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            return base64.b64encode(encrypted).decode("ascii")
        finally:
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)

    @classmethod
    def _dpapi_unprotect(cls, encoded):
        try:
            encrypted = base64.b64decode(encoded)
            in_blob, in_buffer, blob_type = cls._blob(encrypted)
            out_blob = blob_type()
            if not ctypes.windll.crypt32.CryptUnprotectData(
                ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
            ):
                raise SecretStoreError("Windows DPAPI could not decrypt the token.")
            try:
                return ctypes.string_at(out_blob.pbData, out_blob.cbData).decode("utf-8")
            finally:
                ctypes.windll.kernel32.LocalFree(out_blob.pbData)
        except SecretStoreError:
            raise
        except Exception as exc:
            raise SecretStoreError("Stored token is unreadable.") from exc
