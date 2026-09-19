"""Explicit, non-mutating v1 -> v2 migration. Disk is changed only by an explicit save."""

from copy import deepcopy

V1_SHOW = {
    "mode",
    "max_simultaneous",
    "auto_start",
    "fade_in_seconds",
    "hold_seconds",
    "fade_out_seconds",
    "gap_seconds",
    "queue_length",
    "seed",
    "surfaces",
    "scenes",
}


def migrate(data: dict) -> dict:
    if (
        not isinstance(data, dict)
        or type(data.get("schema_version")) is not int
        or data["schema_version"] not in (1, 2)
    ):
        raise ValueError("Unsupported schema_version; expected 1 or 2")
    result = deepcopy(data)
    if result["schema_version"] == 1:
        show = result.get("show", {})
        if set(show) - V1_SHOW or show.get("mode", "shuffle_bag") != "shuffle_bag":
            raise ValueError("Schema 1 cannot contain timeline settings")
        if any(
            "role" in s or "shape" in s or "light" in s for s in result.get("surfaces", [])
        ) or any(s.get("type") == "audio" for s in result.get("scenes", [])):
            raise ValueError("Schema 1 cannot contain version 2 surfaces or audio")
        result["schema_version"] = 2
        result.setdefault("show", {})["timeline"] = {}
    return result
