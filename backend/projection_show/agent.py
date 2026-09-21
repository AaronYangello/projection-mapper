"""Machine-readable discovery contract for automation clients."""

from . import __version__


def agent_manifest(capabilities: dict) -> dict:
    """Describe stable resources, controls, and safety rules without scraping docs."""
    return {
        "interface_version": 1,
        "service": {"name": "Projection Show Engine", "version": __version__},
        "capabilities": capabilities,
        "authentication": {
            "type": "optional_bearer",
            "environment_variable": "PROJECTION_SHOW_TOKEN",
            "note": "The CLI reads the token from the environment; do not put it in arguments.",
        },
        "resources": {
            "snapshot": {"method": "GET", "path": "/api/agent/snapshot"},
            "status": {"method": "GET", "path": "/api/status"},
            "project": {"method": "GET", "path": "/api/project"},
            "media": {"method": "GET", "path": "/api/media"},
            "openapi": {"method": "GET", "path": "/openapi.json"},
        },
        "controls": {
            "runtime": {
                "method": "POST",
                "path_template": "/api/runtime/{action}",
                "actions": [
                    "start",
                    "pause",
                    "resume",
                    "stop",
                    "restart",
                    "skip",
                    "fade-out",
                    "blackout",
                    "restore",
                    "reload",
                ],
                "note": "The response is the resulting status snapshot.",
            },
            "pattern": {
                "method": "PUT",
                "path": "/api/pattern",
                "values": ["show", "grid", "white", "color", "border"],
                "body": {"pattern": "<value>"},
            },
            "manual_play": {
                "method": "POST",
                "path": "/api/manual/play",
                "body": {"surface_id": "<surface id>", "scene_id": "<scene id>"},
                "preconditions": ["shuffle_bag mode", "enabled surface", "available scene"],
            },
            "media_scan": {
                "method": "POST",
                "path": "/api/media/scan",
                "preconditions": ["transport is READY"],
            },
            "project_validate": {
                "method": "POST",
                "path": "/api/project/validate",
                "mutates": False,
            },
            "project_apply": {
                "method": "PUT",
                "path": "/api/project",
                "body": {"revision": "<revision from GET /api/project>", "project": "<Project>"},
                "preconditions": [
                    "transport is READY",
                    "no active deployment",
                    "no active calibration",
                    "revision still matches",
                ],
                "safety": "compare_and_swap_atomic_with_backup",
            },
        },
        "conventions": {
            "success": "Every CLI command writes one JSON document to stdout and exits 0.",
            "failure": "CLI failures write one structured JSON error to stderr and exit non-zero.",
            "revisions": "Read before write. A stale configuration write fails with HTTP 409.",
            "long_running_jobs": (
                "Poll job resources; browser or CLI disconnects do not cancel jobs."
            ),
            "unknown_operations": (
                "Inspect /openapi.json, then use the guarded `agent api` command."
            ),
        },
    }
