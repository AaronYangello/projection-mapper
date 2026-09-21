# Agent and automation interface

The running application exposes a JSON-first control client. It is the preferred interface for
AI agents, shell scripts, and remote operational checks. It uses the same validated API and safety
rules as the web UI; it does not edit YAML behind the running process.

Set the destination once. The bearer token is read from the environment so it does not appear in
the process list or shell history:

```sh
export PROJECTION_SHOW_URL=http://127.0.0.1:8000
export PROJECTION_SHOW_TOKEN='the configured token' # omit when authentication is disabled
```

Start with discovery and one aggregated context snapshot:

```sh
.venv/bin/projection-show agent describe
.venv/bin/projection-show agent snapshot > /tmp/projection-snapshot.json
.venv/bin/projection-show agent project schema > /tmp/project-schema.json
```

`snapshot` is one server-side read containing status, capabilities, the revisioned Project, and the
media index, so those values cannot drift between separate HTTP requests.

Every successful command writes exactly one JSON document to standard output. Operational and
connection errors write a structured JSON error to standard error and exit non-zero. Add
`--compact` before the subcommand for JSONL-friendly single-line output.

## Runtime controls

```sh
.venv/bin/projection-show agent status
.venv/bin/projection-show agent command pause
.venv/bin/projection-show agent command blackout
.venv/bin/projection-show agent command restore
.venv/bin/projection-show agent pattern grid
.venv/bin/projection-show agent pattern show
.venv/bin/projection-show agent play --surface plane-1 --scene coral
.venv/bin/projection-show agent preview --output /tmp/projection-preview.jpg
```

Runtime actions are constrained to the documented action vocabulary. `play` still validates mode,
surface eligibility, and scene availability on the server.
`preview` atomically saves the native GPU output preview and returns JSON metadata, so a visual
agent can inspect the actual composed frame. It refuses to overwrite a file unless `--force` is
given and fails when the native renderer is unavailable.

Use `wait` after a mutation instead of assuming it succeeded at the renderer:

```sh
.venv/bin/projection-show agent wait --transport RUNNING --renderer LIVE --wait-timeout 15
.venv/bin/projection-show agent wait --state READY --wait-timeout 10
```

The timeout result is still JSON, with `matched: false`, and exits with code 4. `--no-warnings`
can be combined with other conditions when a completely clean state is required.

## Safe project edits

Project changes use the server's optimistic revision, Pydantic validation, stopped-state check,
atomic replacement, and last-good backup. Export the wrapper, edit only its nested `project`, and
apply it:

```sh
.venv/bin/projection-show agent project get > /tmp/project-edit.json
# Edit /tmp/project-edit.json, preserving the top-level revision.
.venv/bin/projection-show agent project apply /tmp/project-edit.json
.venv/bin/projection-show agent command stop
.venv/bin/projection-show agent project apply /tmp/project-edit.json --confirm
```

Without `--confirm`, `project apply` is a validation-only dry run. A confirmed bare Project document
must include `--expected-revision`; the safer exported wrapper already carries the revision. If
another operator saves first, the application returns 409 and the agent must fetch, reconcile, and
retry. The CLI never silently stops playback or discards someone else's update.

`project validate FILE` accepts a bare Project or exported wrapper and never saves it. Use `-` as the
file name to read JSON from standard input.

## Media and full API coverage

```sh
.venv/bin/projection-show agent media list
.venv/bin/projection-show agent command stop
.venv/bin/projection-show agent media scan
```

The curated commands cover common inspection and show control. For newer or specialized operations,
read `/openapi.json` (or the browser's `/docs`) and use the guarded raw client:

```sh
.venv/bin/projection-show agent api GET /api/show/timeline
.venv/bin/projection-show agent api POST /api/runtime/seek \
  --data '{"seconds": 12.5}' --confirm-write
.venv/bin/projection-show agent api PUT /api/runtime/audio \
  --data @/tmp/audio-settings.json --confirm-write
```

The raw client accepts only `/api/` paths. Non-GET methods require `--confirm-write`. This provides
coverage for timeline, build, deployment, target, and audio APIs while retaining an obvious mutation
gate. Streaming file transfers should use a purpose-built client until a dedicated CLI command is
added.

## Recommended agent loop

1. Run `describe` once per software version and `snapshot` at the start of a task.
2. Inspect `state`, `transport`, `renderer.status`, `warnings`, `revision`, and `capabilities`.
3. Prefer named commands. Inspect OpenAPI before using `api` for an unfamiliar endpoint.
4. Preserve revisions for configuration writes and perform a dry run before `--confirm`.
5. Use `wait` and then `status` to verify the resulting runtime and renderer state.
6. Leave blackout, test patterns, calibration sessions, and stopped playback only when the task
   explicitly calls for them.
