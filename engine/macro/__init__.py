"""Macro helpers for trading pipeline (no Telegram dependency)."""

from engine.macro.macro_checker import (
    get_upcoming_high_impact_events,
    is_macro_safe_to_trade,
)

__all__ = [
    "get_upcoming_high_impact_events",
    "is_macro_safe_to_trade",
]
