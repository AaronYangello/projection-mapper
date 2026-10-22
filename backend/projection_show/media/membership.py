"""Apply a library selection to saved show sources without touching media files."""

from ..config.models import Project


def update_membership(
    project: Project, entries: list[dict], asset_ids: list[str], action: str
) -> tuple[Project, int]:
    if action not in ("add", "remove"):
        raise ValueError("Choose add or remove")
    indexed = {entry["id"]: entry for entry in entries}
    if any(asset_id not in indexed for asset_id in asset_ids):
        raise ValueError("Selected files changed; scan the folder and select again")
    selected = [indexed[asset_id] for asset_id in dict.fromkeys(asset_ids)]
    data = project.model_dump(mode="json")
    changed = 0
    if action == "add":
        sources = {s.get("path"): s for s in data["scenes"] if s["type"] != "color"}
        ids = {s["id"] for s in data["scenes"]}
        for entry in selected:
            if entry["error"]:
                continue
            source = sources.get(entry["path"])
            included = source is not None and source["enabled"]
            if source is None:
                scene_id = entry["id"]
                suffix = 2
                while scene_id in ids:
                    scene_id = f"{entry['id']}-{suffix}"
                    suffix += 1
                source = {
                    "id": scene_id,
                    "name": entry["name"],
                    "type": entry["type"],
                    "path": entry["path"],
                    "fit": "cover",
                    "enabled": True,
                }
                data["scenes"].append(source)
                sources[entry["path"]] = source
                ids.add(scene_id)
            else:
                source["enabled"] = True
            if project.show.shuffle_media_mode == "selected" and entry["type"] != "audio":
                paths = data["show"]["shuffle_media_paths"]
                included = included and entry["path"] in paths
                if entry["path"] not in paths:
                    paths.append(entry["path"])
            changed += not included
    else:
        paths = {entry["path"] for entry in selected}
        removed = {s.id for s in project.scenes if s.type != "color" and s.path in paths}
        changed = len({s.path for s in project.scenes if s.id in removed})
        data["scenes"] = [s for s in data["scenes"] if s["id"] not in removed]
        if project.show.shuffle_media_mode == "all_folder" and removed:
            # A folder-wide policy would immediately re-add the removed sources.
            # Freeze the remaining folder membership as an explicit selection.
            data["show"]["shuffle_media_mode"] = "selected"
            data["show"]["shuffle_media_paths"] = [
                entry["path"]
                for entry in entries
                if entry["type"] in ("video", "image")
                and not entry["error"]
                and entry["path"] not in paths
            ]
        else:
            data["show"]["shuffle_media_paths"] = [
                path for path in project.show.shuffle_media_paths if path not in paths
            ]
        timeline = data["show"]["timeline"]
        for track in timeline["tracks"]:
            track["clips"] = [clip for clip in track["clips"] if clip["scene_id"] not in removed]
        if timeline.get("audio") and timeline["audio"]["scene_id"] in removed:
            timeline["audio"] = None
    return Project.model_validate(data), changed
