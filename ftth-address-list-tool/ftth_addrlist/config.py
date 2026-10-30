"""Configuration loading: built-in defaults merged with an optional regional file."""

from __future__ import annotations

import copy
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - older Python
    import tomli as tomllib  # type: ignore

TOOL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = TOOL_ROOT / "config" / "default_config.toml"


class ConfigError(Exception):
    pass


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_config(path: str | Path | None = None) -> dict:
    """Return the default configuration, overlaid with `path` when given."""
    if not DEFAULT_CONFIG.exists():
        raise ConfigError(f"Default configuration missing: {DEFAULT_CONFIG}")
    with open(DEFAULT_CONFIG, "rb") as fh:
        cfg = tomllib.load(fh)
    if path:
        path = Path(path)
        if not path.exists():
            raise ConfigError(f"Configuration file not found: {path}")
        try:
            with open(path, "rb") as fh:
                cfg = _merge(cfg, tomllib.load(fh))
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"Configuration file {path} is not valid TOML: {exc}") from exc
    _validate(cfg)
    cfg["_source"] = str(path) if path else str(DEFAULT_CONFIG)
    return cfg


def _validate(cfg: dict) -> None:
    fields = {"pon_name", "pon_port", "fiber_no", "address", "tube_color", "fiber_color",
              "cable_name", "tap_name", "fiber_splice"}
    cols = cfg.get("template", {}).get("columns", [])
    if not cols:
        raise ConfigError("template.columns is empty")
    for col in cols:
        if col.get("field") not in fields:
            raise ConfigError(f"Unknown field key in template.columns: {col.get('field')!r}")
    seq = cfg["colors"]["sequence"]
    missing = [c for c in seq if c not in cfg["colors"]["abbreviations"]]
    if missing:
        raise ConfigError(f"colors.abbreviations missing entries for {missing}")
    if cfg["fiber_splice"]["missing_report_policy"] not in ("provisional", "unresolved"):
        raise ConfigError("fiber_splice.missing_report_policy must be 'provisional' or 'unresolved'")
    hv = cfg["fiber_splice"].get("hub_value_sections", "all")
    if hv not in ("all", "feeder", "feeder_and_first_distribution", "none"):
        raise ConfigError("fiber_splice.hub_value_sections must be 'all', 'feeder', "
                          "'feeder_and_first_distribution' or 'none'")


def resolve_tool_path(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else TOOL_ROOT / path
