"""
config_loader.py — Centralized config loading with API key overlay.

Loads autonomous_trading.yaml as the base config, then overlays
config/api_keys.yaml on top. This means:
  - autonomous_trading.yaml can be SCP'd freely without losing keys
  - api_keys.yaml is excluded from git and SCP (written by GitHub Actions)
  - Local dev: populate api_keys.yaml manually

Usage:
    from src.core.config_loader import load_config
    config = load_config()  # returns merged dict
"""

import logging
from pathlib import Path
from typing import Dict, Any

import yaml

logger = logging.getLogger(__name__)

_BASE_CONFIG_PATH = Path("config/autonomous_trading.yaml")
_KEYS_PATH = Path("config/api_keys.yaml")

_cached_config: Dict[str, Any] | None = None


def load_config(force_reload: bool = False) -> Dict[str, Any]:
    """
    Load the merged config: autonomous_trading.yaml + api_keys.yaml overlay.

    Caches the result in memory. Call with force_reload=True after a key rotation.
    """
    global _cached_config
    if _cached_config is not None and not force_reload:
        return _cached_config

    # Load base config
    config: Dict[str, Any] = {}
    if _BASE_CONFIG_PATH.exists():
        with open(_BASE_CONFIG_PATH) as f:
            config = yaml.safe_load(f) or {}
    else:
        logger.warning(f"Base config not found: {_BASE_CONFIG_PATH}")

    # Overlay API keys
    if _KEYS_PATH.exists():
        with open(_KEYS_PATH) as f:
            keys = yaml.safe_load(f) or {}

        ds = config.setdefault("data_sources", {})

        for provider, values in keys.items():
            if not isinstance(values, dict):
                continue
            api_key = values.get("api_key")
            if not api_key or api_key == "REPLACE_VIA_SECRETS_MANAGER":
                continue
            # Merge into data_sources section
            if provider not in ds:
                ds[provider] = {}
            ds[provider]["api_key"] = api_key
            logger.debug(f"API key loaded for {provider} from api_keys.yaml")
    else:
        logger.debug("api_keys.yaml not found — using keys from autonomous_trading.yaml")

    _cached_config = config
    return config


def get_api_key(provider: str) -> str | None:
    """Convenience: get a single API key by provider name."""
    config = load_config()
    return config.get("data_sources", {}).get(provider, {}).get("api_key")
