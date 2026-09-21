# API operations (v0.3)

The running server's `/docs` and `/openapi.json` contain exact typed request schemas.
`/api/live` publishes copied playback status; native JPEG preview is captured from the GPU.
Jobs are polled independently, so a browser disconnect cannot cancel a build or stop playback.

All ordinary `/api` operations use the configured bearer token. Browser writes also require
same-origin requests; no wildcard CORS bypass is added. Deployment writes require a token to
be configured even if read-only status is open. Authentication headers/secrets must never be
logged. The one-time download GET uses its own scoped cookie authorization.

`GET /api/agent/manifest` provides a compact machine-readable discovery contract with common
resources, controls, preconditions, and safety conventions. The bundled `projection-show agent`
client consumes this API and emits JSON-only results; see the [agent interface](agent-interface.md).

## Authoring and runtime

| Method / path | Body / behavior |
| --- | --- |
| GET `/api/capabilities` | Explicit role, compiler availability, deployment permission/reason |
| GET `/api/show/timeline` | Saved timeline and revision |
| PUT `/api/show/timeline` | `{revision, timeline}`; stopped authoring save, full reference/range validation |
| POST `/api/show/mode` | `{revision, mode: "shuffle_bag" or "timeline"}`; explicit stopped activation |
| POST `/api/runtime/seek` | `{seconds}`; finite absolute timeline position |
| GET/PUT `/api/runtime/audio` | `audio_sink` auto/alsa/fake, `audio_device`, nullable volume/muted/sync_offset_ms; machine-local, routing stopped-only |
| POST `/api/runtime/{command}` | Existing start/pause/resume/stop/blackout/restore/skip/fade controls |

The full project and mapping APIs retain optimistic revisions and calibration leases.
409 indicates stale state, invalid operational timing or incompatible input. Typed validation
uses 422. An authoring role is required to save timeline/mode or invoke the compiler.

## Streamed media

1. POST `/api/media/uploads` with `{name, size}` while stopped to reserve a bounded job.
2. POST `/api/media/upload?upload_id=<id>` with raw bytes; the server streams to disk.
3. GET `/api/media/uploads/{id}` reports received bytes/state/error/result.
4. DELETE `/api/media/uploads/{id}` cancels; also abort the browser request.
5. Explicitly scan/add/save after success. Upload never creates a scene or starts playback.

The actual content is probed and hashed; declared extension/MIME is insufficient. Limits,
safe final names, duplicate detection, atomic install and cleanup are in [storage](build-deploy.md#storage-limits).

## Builds

| Method / path | Behavior |
| --- | --- |
| POST `/api/builds/inspect` | Hash/probe saved inputs; return exact staleness category versus latest build |
| POST `/api/builds` | `{revision, profile: "pi4-1080p", encoder: "auto"}`; enqueue immutable saved snapshot |
| GET/DELETE `/api/builds/{id}` | Job progress/result/error or cancellation (shared job registry) |
| GET `/api/builds/latest` | Latest completed artifact record |
| GET `/api/builds/{id}/bundle`, `/api/builds/latest/bundle` | Authenticated streamed ZIP download |
| POST `/api/builds/latest/download` | Issue one-use 60-second scoped HttpOnly/SameSite cookie |
| GET `/api/builds/download` | Consume download ticket and stream; no bearer in URL |
| POST `/api/builds/latest/preview` | Validate/load authoring preview while stopped; no active-pointer mutation |
| POST `/api/builds/preview/unload` | Stop-only return to local project |

## Destination and remote deployment

POST `/api/deployments/upload` streams raw ZIP bytes with a positive bounded Content-Length.
It returns an install job; poll/cancel it through `/api/builds/{id}`. Completed validation
stages a version but does not activate. GET `/api/deployments` lists active/previous IDs,
versions and compatibility information. Activation, rollback and unload are stopped-only:

- POST `/api/deployments/{id}/activate`
- POST `/api/deployments/rollback`
- POST `/api/deployments/unload`

Each requires `{confirmed: true, expected_active: <id or null>}`. The server revalidates
media and destination compatibility, then rechecks stopped/revision/current-ID state before
atomic activation. A stale confirmation fails instead of replacing a newer show.

GET/PUT `/api/target` manages machine-local `{url, token}`; reads return `token_saved` only.
Null/blank token preserves the existing secret. POST `/api/target/test` performs read-only
connection checks. POST `/api/target/deploy` requires the confirmation fields plus exact
`bundle_id` and `target_url`. Its job reports remote upload/validation/activation progress and
returned active ID. No redirects, public origins, environment proxies, arbitrary paths or
shell commands are accepted. After an ambiguous network failure at activation, read the
remote active state before retrying. See [deployment semantics](build-deploy.md).
