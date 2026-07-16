import os
from pathlib import Path


ALIZA_DOTENV_ENABLED = "ALIZA_DOTENV_ENABLED"

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def dotenv_enabled(*, default: bool = True) -> bool:
    raw_value = os.getenv(ALIZA_DOTENV_ENABLED)
    if raw_value is None:
        return default

    normalized_value = raw_value.strip().lower()
    if normalized_value in _TRUE_VALUES:
        return True
    if normalized_value in _FALSE_VALUES:
        return False

    raise RuntimeError(
        f"{ALIZA_DOTENV_ENABLED} must be one of: "
        "1, true, yes, on, 0, false, no, off."
    )


def _project_dotenv_path() -> Path:
    return Path(__file__).resolve().parent.parent / ".env"


def load_project_dotenv(*, default_enabled: bool = True) -> bool:
    if not dotenv_enabled(default=default_enabled):
        return False

    from dotenv import load_dotenv

    return bool(
        load_dotenv(
            dotenv_path=_project_dotenv_path(),
            override=False,
        )
    )
