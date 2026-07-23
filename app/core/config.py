"""Backward-compatible settings import; prefer :mod:`app.core.settings`."""

from app.core.settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]
