"""Secure API key storage via Windows Credential Manager (keyring).

Usage:
    from core.secrets import get_key, set_key, get_all_keys, migrate_from_config

Keys are stored in Windows Credential Manager under service "AXIS_OS".
Falls back to plaintext values when keyring is unavailable.
"""
import os

_SERVICE = "AXIS_OS"
_keyring = None
_keyring_checked = False


def _kr():
    """Lazy-load keyring once; returns None if unavailable."""
    global _keyring, _keyring_checked
    if _keyring_checked:
        return _keyring
    _keyring_checked = True
    try:
        import keyring
        # Quick smoke-test to confirm the backend works
        keyring.get_password(_SERVICE, "__test__")
        _keyring = keyring
    except Exception:
        _keyring = None
    return _keyring


def get_key(name: str, fallback: str = "") -> str:
    """Read a key from Credential Manager; return fallback if not found."""
    kr = _kr()
    if kr:
        try:
            val = kr.get_password(_SERVICE, name)
            if val:
                return val
        except Exception:
            pass
    return fallback


def set_key(name: str, value: str) -> bool:
    """Store a key in Credential Manager. Returns True on success."""
    kr = _kr()
    if not kr:
        print(f"[AXIS] ⚠ Keyring unavailable — key for '{name}' NOT saved to Credential Manager (will use config.json fallback)")
        return False
    try:
        if value:
            kr.set_password(_SERVICE, name, value)
        else:
            try:
                kr.delete_password(_SERVICE, name)
            except Exception:
                pass
        return True
    except Exception:
        return False


def delete_key(name: str) -> None:
    """Remove a key from Credential Manager."""
    kr = _kr()
    if not kr:
        return
    try:
        kr.delete_password(_SERVICE, name)
    except Exception:
        pass


def get_all_keys(fallback_dict: dict) -> dict:
    """Return merged dict: Credential Manager values override fallback_dict.

    Call this everywhere instead of cfg.get("api_keys", {}).
    """
    result = dict(fallback_dict)
    kr = _kr()
    if not kr:
        return result
    for name in list(result.keys()):
        try:
            val = kr.get_password(_SERVICE, name)
            if val:
                result[name] = val
        except Exception:
            pass
    # Also try fetching from keyring for common provider names not yet in result
    KNOWN_PROVIDERS = ['openai', 'anthropic', 'gemini', 'xai', 'perplexity', 'ollama', 'groq', 'deepseek']
    for provider in KNOWN_PROVIDERS:
        if provider not in result:
            try:
                val = kr.get_password(_SERVICE, provider)
                if val:
                    result[provider] = val
            except Exception:
                pass
    return result


def migrate_from_config(api_keys: dict) -> int:
    """Move API keys from plaintext dict into Credential Manager.

    Returns count of successfully migrated keys.
    Skips keys that already exist in Credential Manager to avoid
    overwriting newer keys with stale values from config.json.
    """
    count = 0
    for name, value in list(api_keys.items()):
        if not (value and isinstance(value, str)):
            continue
        existing = get_key(name)
        if existing:
            api_keys[name] = ""  # wipe from plaintext, keyring already has it
            count += 1
            continue
        if set_key(name, value):
            api_keys[name] = ""  # wipe from plaintext
            count += 1
    return count


def keyring_available() -> bool:
    """True if Windows Credential Manager backend is working."""
    return _kr() is not None
