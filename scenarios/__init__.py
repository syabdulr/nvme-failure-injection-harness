"""Scenario registry."""
from __future__ import annotations

from scenarios.base import InjectionResult, Scenario
from scenarios.compare_mismatch import CompareMismatch
from scenarios.invalid_opcode import InvalidOpcode
from scenarios.media_error import MediaError
from scenarios.oob_write import OobWrite
from scenarios.smart_warning import SmartWarning

_ALL = [OobWrite(), InvalidOpcode(), CompareMismatch(), MediaError(), SmartWarning()]
REGISTRY = {s.name: s for s in _ALL}

# scenarios that need no special device configuration — one VM boot runs them all
CLIENT_SIDE = [s.name for s in _ALL if not s.needs_blkdebug and not s.device_props]


def get(name: str) -> Scenario:
    try:
        return REGISTRY[name]
    except KeyError:
        raise SystemExit(f"unknown scenario '{name}'. known: {', '.join(REGISTRY)}")


def names() -> list[str]:
    return list(REGISTRY)


__all__ = ["REGISTRY", "CLIENT_SIDE", "get", "names", "Scenario", "InjectionResult"]
