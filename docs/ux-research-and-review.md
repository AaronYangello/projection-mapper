# Video utility UX research and implementation review

2026-09-18. Scope: the working desktop engine and browser controls, for one operator using
configurable installations. This is a research-informed implementation review with live checks,
not a usability study with representative participants or a claim of user approval.

## Findings and sources

| Source | Finding applied to this app |
| --- | --- |
| [Nielsen Norman Group: usability heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/) | Show system state, use familiar language, give edits an exit, and favor recognition over recall. Put the consequence beside a control and preserve the operator's work. |
| [MadMapper: media bin](https://docs.madmapper.com/madmapper/6/3.-media/media-bin) | A media library and selected-item inspector are useful separate contexts. Selection should be distinguishable from sending content to an output. |
| [Resolume: layouts](https://www.resolume.com/support/en/layouts) and [clip time panel](https://www.resolume.com/support/en/clip-time-panel) | Preview/output monitors and clip timing belong close to the operational workspace. Our current cue, time remaining, output image, and queue share one Playback page. |
| [WCAG 2.2](https://www.w3.org/TR/WCAG22/) | Check contrast, focus, control labels, status messages, and pointer targets. Provide an alternative to dragging. The minimum target criterion is 24 CSS px with exceptions; 44 px is the enhanced criterion and our mapping-handle/nudge target. |
| [OpenAI: designing frontends](https://developers.openai.com/blog/designing-delightful-frontends-with-gpt-5-4) | The app-oriented guidance favors a primary workspace, navigation, contextual inspectors, restrained accents, readable density, and utility copy. Cards and marketing copy should earn their place. |
| [Anthropic: frontend design patterns](https://claude.com/blog/improving-frontend-design-through-skills) | Repeated model defaults such as predictable typography/gradient/component combinations can produce generic designs. This is vendor guidance, not evidence that any one font, gradient, or card harms usability. |
| [Shin et al.: design homogenization in web vibe coding](https://arxiv.org/abs/2603.13036) | This preprint analyzes homogenization risks and proposes mitigation; it is not a measured usability ranking of this app or this model. Treat generated defaults as choices to examine against tasks. |

Novelty is not the objective here. Familiar buttons, a system font, dark controls, thumbnails,
and grouped settings are useful for this tool. A distinctive skin would not compensate for
lost drafts, hidden output modes, or unclear playback behavior.

## Self-audit of the first implementation

Observed in the code and live interface I previously generated:

- Duplicate Dashboard and Runtime previews, with inventory counts taking a separate route.
- Large page headings, repeated eyebrow labels, decorative tagline copy, and substantial chrome.
- Many secondary labels at 9–11 px with weak contrast on a green-tinted palette.
- Internal wording such as Runtime, READY, shuffle bag, and decoder plumbing in routine flows.
- Media controls exposed settings but offered no search, no clear saved confirmation, and lost
  local edits on page changes. Mapping silently discarded unsaved corners on navigation.
- The background-motion claim stayed visible during pause/blackout. Stop and fade controls
  did not make ambient-only output and advancement to the next cue clear enough.

These are observed defaults in this implementation, not claims of access to hidden model
training data. There was no purple gradient to remove. The changes target actual friction.

## Implemented decisions

| Area | Result |
| --- | --- |
| Navigation | Five visible workspaces: Playback, Mapping, Media, Project, Diagnostics. Playback combines the former runtime/overview; Project and Diagnostics retain configuration and health information. Page choice persists within the browser session; changing workspace starts at its top. |
| Playback | Current cue precedes the actual GPU capture; queue stays adjacent on wide screens. Persistent transport, explicit Stop show/Fade to next wording, visible blackout explanation, and a Return to content action for test patterns. Space controls transport only outside form/interactive elements. |
| Mapping | Fit/zoom editing, 44 px corner handles, four tap-to-nudge buttons, 1/10 px steps, undo/redo, disclosed exact coordinates, saved confirmation, and protected navigation. Mobile Start mapping brings the quad into view. |
| Media | Search names/paths/tags, filter video/image/errors, show library membership, preserve thumbnail aspect ratio, expose the actual media folder path, and distinguish file selection from Play on surface. Display name, enabled state, fit, clip timing, crop center, and tags are editable with explicit save/discard feedback. |
| Drafts | Media and project drafts survive page navigation. Leaving dirty mapping or choosing another media asset offers Keep editing/Discard. Browser unload is guarded. An incoming project change preserves a dirty draft and blocks a stale full-project overwrite. |
| Project | Existing projectors/surfaces can be renamed, enabled, assigned, and sized with forms. Background and foreground eligibility are exposed. Complete JSON stays available for unrestricted topology and advanced configuration. |
| Diagnostics | Operational test patterns remain real native-output controls with their effect stated. Metrics and event history stay available without decorative status dashboards on the main path. |
| Visual/accessibility | Neutral dark canvas, blue edit/action accent, green healthy state, readable 12–14 px secondary text, stronger borders/focus, text state labels, and all five phone navigation destinations visible without a hidden horizontal strip. |

Representative interaction change:

```diff
- setPage(next); // mapping unmount discards an unsaved preview
+ if (mappingDirty) offerKeepEditingOrDiscard(next);
+ else navigate(next);
```

The renderer, native decoder, generic topology, queue rules, and atomic persistence remain the
same. The API additionally reports the configured media folder so the UI can identify where
files belong. No cloud service or installation-specific layout is introduced.

## Verification

- 63 backend/native tests, including 6 real GPU tests, pass on the Mac. These retain video,
  warp, pause/blackout, calibration lease, persistence, and error-recovery coverage.
  The app shell disables caching so a reload after a frontend rebuild loads the current interface.
- 11 browser regression tests pass. The suite runs against a disposable API-only project, with synthetic images,
  a native-encoded sample clip, and an intentionally corrupt file. It never edits the user's
  project. Run `cd frontend && npm run test:ui`; installed Google Chrome is the default browser.
- Browser checks cover navigation/reflow at 1440, 768, and 390 px; media selection/save; draft
  preservation/conflicts; mapping nudge/undo/redo/save/discard; blackout/pattern exit; library
  empty/error states; topology form persistence; and keyboard shortcut isolation.
- Native review uses an independent copied project at port 8001, exercising actual GPU output
  and media rather than treating the API-only tests as proof of rendered pixels. Browser-emulated
  touch dragging moved a corner, revert restored it, and the actual H.264 trailer decoded with
  READY state while the renderer reported 60 FPS on this Mac.
- Measured primary secondary-text colors against the panel background: 8.24:1 for muted text,
  10.70:1 for field labels, and 8.75:1 for action text. These spot checks are not full WCAG
  certification. Mapping/nudge targets are 44 px; keyboard focus and modal escape were checked.
- All viewport reviews use the product's supported dark theme. Light mode is not implemented.
  Physical phone/LAN and Raspberry Pi hardware remain outside this desktop evidence.

Review screenshots are ignored artifacts under `artifacts/ux-*`. The review includes temporary
synthetic media only in the copied review project. User project configuration is preserved.

## Remaining limits

At the v0.2 baseline, import used the local folder. v0.3 adds explicit streamed upload;
remote deletion and general file management remain out of scope.
The media inspector shows a representative still thumbnail, not a private video audition player
or trim timeline. Advanced JSON still handles adding/removing topology and detailed ambient
profiles. These remain visible capability boundaries rather than disconnected controls.

## Timeline and deployment review · v0.3

The new Show workspace extends the existing Playback-centered navigation. Its Shuffle and
Timeline tabs edit saved definitions without activating them. Use this mode is explicit and
stopped-only. Source editing remains in third-party NLEs; this workspace aligns tracks,
master audio, lights and full-surface opacity. A local controlled view adapter avoids exposing
NLE tools that the engine does not implement. The bounded MIT/React-compatibility/grouping/
keyboard spike for react-timeline-editor is recorded in [implementation decisions](timeline-implementation.md).

The design applies the earlier research to concrete tasks: stable surface/projector names,
absolute time with numeric alternatives, snap/zoom/pan, visible opacity curves, explicit
save/discard/conflict handling, and simple fade/visible/dark actions. Projector groups cannot
become accidental drag/drop reassignment targets. Phone authoring is a labeled overview;
blackout, runtime, mapping, uploads and deployment retain usable controls.

Build feedback distinguishes expensive video changes from audio remux, metadata changes and
mapping-only edits. Native browser export streams files rather than loading whole bundles in
JavaScript. Target secrets are masked behind Edit. Deployment confirmation names the target,
new bundle and prior state, and the result reads back the destination ID. Disabled capability
controls explain compiler/auth requirements. Operational diagnostics stay secondary to editing.

Final evidence and exact test counts are in [verification](verification.md). Reviews use the
supported dark theme, 1440×900 desktop, 768×1024 tablet and 390×844 phone. Interactive native
review uses an isolated four-video/sixteen-light fixture; browser regression tests use a
disposable API-only fixture. Synthetic remote confirmation tests are not real Pi deployment.
No user approval or physical-device usability result is inferred from automated checks.
