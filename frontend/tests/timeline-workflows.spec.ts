import { test, expect, type Page } from "@playwright/test";

let original: any;
const nav = (p: Page, name: string) =>
  p.getByRole("navigation").getByRole("button", { name, exact: true });
test.beforeAll(async ({ request }) => {
  original = (await (await request.get("/api/project")).json()).project;
});
test.beforeEach(async ({ page, request }) => {
  await request.post("/api/runtime/stop");
  await request.post("/api/builds/preview/unload");
  const { revision } = await (await request.get("/api/project")).json();
  const p = structuredClone(original);
  p.canvas = { ...p.canvas, width: 1920, height: 1080, refresh_rate: 30 };
  p.projectors = [
    { ...p.projectors[0], viewport: { x: 0, y: 0, width: 1920, height: 1080 } },
  ];
  p.surfaces = p.surfaces
    .slice(0, 4)
    .map((s: any) => ({ ...s, projector_id: p.projectors[0].id }));
  p.show = {
    ...p.show,
    mode: "shuffle_bag",
    auto_start: false,
    timeline: {
      duration_seconds: 4,
      loop: false,
      track_order: [],
      tracks: [],
      audio: null,
    },
  };
  expect(
    (
      await request.put("/api/project", { data: { revision, project: p } })
    ).ok(),
  ).toBeTruthy();
  await page.goto("/");
  // Private-network HTTP does not expose the secure-context randomUUID API.
  await page.evaluate(() =>
    Object.defineProperty(crypto, "randomUUID", {
      value: undefined,
      configurable: true,
    }),
  );
  await nav(page, "Show").click();
});

test("authoring tabs do not activate; stopped explicit action preserves both definitions", async ({
  page,
  request,
}) => {
  await expect(page.getByText("Active mode:")).toContainText("Shuffle");
  await page.getByRole("tab", { name: "Timeline", exact: true }).click();
  expect((await (await request.get("/api/status")).json()).mode).toBe(
    "shuffle_bag",
  );
  await page.getByRole("button", { name: "Start show", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Use this mode", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Stop show", exact: true }).click();
  await page
    .getByRole("button", { name: "Use this mode", exact: true })
    .click();
  await expect(page.getByText("Active mode:")).toContainText("Timeline");
  const p = (await (await request.get("/api/project")).json()).project;
  expect(p.show.fade_in_seconds).toBe(original.show.fade_in_seconds);
  expect(p.show.timeline.duration_seconds).toBe(4);
});

test("clips, duplicate, overlap rejection, opacity edits and draft preservation", async ({
  page,
  request,
}) => {
  await page.getByLabel("Duration (s)", { exact: true }).fill("1");
  await page.getByRole("button", { name: "Add clip", exact: true }).click();
  const clip = page.locator(".timeline-clip").first();
  await clip.click();
  await page.getByLabel("Start (s)", { exact: true }).fill("1");
  await page
    .getByRole("button", { name: "Apply clip fields", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Duplicate after", exact: true })
    .click();
  expect(await page.locator(".timeline-clip").count()).toBe(2);
  // Drag first clip half a second into its neighbor; reject without ripple movement.
  await clip.scrollIntoViewIfNeeded();
  const box = await clip.boundingBox();
  await page.mouse.move(box!.x + 20, box!.y + 10);
  await page.mouse.down();
  await page.mouse.move(box!.x + 95, box!.y + 10);
  await page.mouse.up();
  await expect(page.getByRole("alert")).toContainText("cannot overlap");
  await page.getByRole("button", { name: "Fade in", exact: true }).click();
  const point = page.getByRole("button", { name: /opacity point 1$/ }).first();
  await point.click();
  await point.press("ArrowUp");
  await expect(page.getByLabel("Opacity (0–1)", { exact: true })).toHaveValue(
    "0.05",
  );
  await nav(page, "Media").click();
  await nav(page, "Show").click();
  await expect(
    page.getByText("Unsaved timeline draft", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Save timeline", exact: true })
    .click();
  await expect(page.getByText("Timeline saved", { exact: true })).toBeVisible();
  const t = (await (await request.get("/api/project")).json()).project.show
    .timeline;
  expect(t.tracks[0].clips.map((c: any) => c.start_seconds)).toEqual([1, 2]);
  expect(t.tracks[0].opacity.keyframes[0].value).toBeCloseTo(0.05);
});

test("projector groups collapse and row order never reassigns a surface", async ({
  page,
  request,
}) => {
  const before = (await (await request.get("/api/project")).json()).project;
  const group = page.locator(".projector-group").first();
  await group.click();
  await expect(page.locator(".surface-lane")).toHaveCount(0);
  await group.click();
  await expect(page.locator(".surface-lane")).toHaveCount(4);
  await page
    .getByRole("button", {
      name: `Move ${before.surfaces[0].name} down`,
      exact: true,
    })
    .click();
  await page
    .getByRole("button", { name: "Save timeline", exact: true })
    .click();
  await expect(page.getByText("Timeline saved", { exact: true })).toBeVisible();
  const after = (await (await request.get("/api/project")).json()).project;
  expect(after.show.timeline.track_order.slice(0, 2)).toEqual([
    before.surfaces[1].id,
    before.surfaces[0].id,
  ]);
  expect(after.surfaces.map((s: any) => s.projector_id)).toEqual(
    before.surfaces.map((s: any) => s.projector_id),
  );
});

test("remote revision keeps a timeline draft and blocks stale save", async ({
  page,
  request,
}) => {
  await page.getByRole("button", { name: "Set dark", exact: true }).click();
  const current = await (await request.get("/api/project")).json();
  current.project.name = "Edited elsewhere";
  await request.put("/api/project", { data: current });
  await expect(
    page.getByText("Your timeline draft is retained.", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Save timeline", exact: true }),
  ).toBeDisabled();
  await expect(page.getByLabel("Default opacity", { exact: true })).toHaveValue(
    "0",
  );
});

test("real build, staleness and streamed export; remote confirmation is synthetic", async ({
  page,
  request,
}) => {
  await page
    .getByRole("button", { name: "Use this mode", exact: true })
    .click();
  await page.getByLabel("Duration (s)", { exact: true }).fill("2");
  await page.getByRole("button", { name: "Add clip", exact: true }).click();
  await page
    .getByRole("button", { name: "Save timeline", exact: true })
    .click();
  await expect(page.getByText("Timeline saved", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Build & Deploy", exact: true }).click();
  await page.getByRole("button", { name: "Build", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "build · complete", exact: true }),
  ).toBeVisible({ timeout: 20000 });
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Export bundle", exact: true })
    .click();
  expect((await download).suggestedFilename()).toMatch(/\.pshow$/);
  await page
    .getByRole("button", { name: "Check build inputs", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Build current." }).first(),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Timeline", exact: true }).click();
  await page.getByRole("button", { name: "Set dark", exact: true }).click();
  await page
    .getByRole("button", { name: "Save timeline", exact: true })
    .click();
  await expect(page.getByText("Timeline saved", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Build & Deploy", exact: true }).click();
  await page
    .getByRole("button", { name: "Check build inputs", exact: true })
    .click();
  await expect(page.getByText(/Metadata update only:/)).toBeVisible();
  await page.getByRole("button", { name: "Edit target", exact: true }).click();
  await page.getByLabel("Pi URL", { exact: true }).fill("http://127.0.0.1:9");
  await page
    .getByLabel("Bearer token", { exact: true })
    .fill("synthetic-only-test-value");
  await page.getByRole("button", { name: "Save target", exact: true }).click();
  await expect(page.getByText(/Token •••••••• saved/)).toBeVisible();
  // No Pi exists. Only the target response is intercepted, never the build or saved project.
  await page.route("**/api/target/test", (route) =>
    route.fulfill({
      json: {
        id: "connection",
        kind: "connection",
        state: "complete",
        progress: 1,
        result: {
          connected: true,
          capabilities: { role: "appliance" },
          active: "previous",
        },
      },
    }),
  );
  let dispatched = false;
  await page.route("**/api/target/deploy", async (route) => {
    dispatched = true;
    const body = route.request().postDataJSON();
    expect(body.confirmed).toBe(true);
    expect(body.expected_active).toBe("previous");
    await route.fulfill({
      json: {
        id: "deploy",
        kind: "deploy",
        state: "complete",
        progress: 1,
        result: { activation_confirmed: true, active: body.bundle_id },
      },
    });
  });
  await page
    .getByRole("button", { name: "Build & Deploy", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  expect(dispatched).toBe(false);
  await page
    .getByRole("button", { name: "Keep current show", exact: true })
    .click();
  expect(dispatched).toBe(false);
  await page
    .getByRole("button", { name: "Build & Deploy", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Confirm activation", exact: true })
    .click();
  await expect(
    page.getByText(/Target confirmed active deployment:/),
  ).toBeVisible();
  expect(dispatched).toBe(true);
  expect(
    (await (await request.get("/api/deployments")).json()).active,
  ).toBeNull();
});

test("media upload probes, detects duplicates, reports errors and cancels", async ({
  page,
  request,
}) => {
  await nav(page, "Media").click();
  const assets = (await (await request.get("/api/media")).json()).assets;
  const data = await (
    await request.get(
      `/api/media/${assets.find((a: any) => a.type === "image").id}/thumbnail`,
    )
  ).body();
  const input = page.getByLabel("Drop media here or choose files", {
    exact: true,
  });
  await input.setInputFiles({
    name: "browser-upload.jpg",
    mimeType: "image/jpeg",
    buffer: data,
  });
  await expect(page.getByText(/Uploaded · scan to index/)).toBeVisible();
  await input.setInputFiles({
    name: "duplicate.jpg",
    mimeType: "image/jpeg",
    buffer: data,
  });
  await expect(page.getByText(/Already in library/)).toBeVisible();
  await input.setInputFiles({
    name: "corrupt.mp4",
    mimeType: "video/mp4",
    buffer: Buffer.from("not video"),
  });
  await expect(
    page.getByRole("alert").filter({ hasText: /Cannot install/ }),
  ).toBeVisible();
  let finish: () => void = () => {};
  await page.route("**/api/media/upload?*", async (route) => {
    await new Promise<void>((resolve) => {
      finish = resolve;
    });
    await route.abort().catch(() => {});
  });
  await input.setInputFiles({
    name: "cancel.jpg",
    mimeType: "image/jpeg",
    buffer: data,
  });
  await page
    .getByRole("button", { name: "Cancel upload", exact: true })
    .click();
  finish();
  await expect(
    page.getByRole("status").filter({ hasText: "Cancelled" }),
  ).toBeVisible();
});

test("phone timeline is an overview; runtime, deployment and blackout remain available", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByText(/Timeline overview on phone/)).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Save timeline", exact: true }),
  ).toBeDisabled();
  await page.getByRole("tab", { name: "Build & Deploy", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Build", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Blackout", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Restore output", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Restore output", exact: true })
    .click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("synthetic rollback requires review and displays activation failure", async ({
  page,
}) => {
  let active = "current-bundle";
  let previous = "previous-bundle";
  let calls = 0;
  let fail = true;
  await page.route("**/api/capabilities", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      json: {
        ...(await response.json()),
        deployment_write: true,
        deployment_reason: null,
      },
    });
  });
  await page.route("**/api/deployments", (route) =>
    route.fulfill({ json: { active, previous, deployments: [] } }),
  );
  await page.route("**/api/deployments/rollback", async (route) => {
    calls++;
    expect(route.request().postDataJSON()).toEqual({
      confirmed: true,
      expected_active: active,
    });
    if (fail)
      await route.fulfill({
        status: 409,
        json: {
          detail: "Previous bundle checksum failed; current show retained",
        },
      });
    else {
      [active, previous] = [previous, active];
      await route.fulfill({ json: { active, previous } });
    }
  });
  await page.reload();
  await nav(page, "Show").click();
  await page.getByRole("tab", { name: "Build & Deploy", exact: true }).click();
  await page.getByRole("button", { name: "Roll back", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("previous-bundle");
  await expect(page.getByRole("dialog")).toContainText("current-bundle");
  await page
    .getByRole("button", { name: "Keep current show", exact: true })
    .click();
  expect(calls).toBe(0);
  await page.getByRole("button", { name: "Roll back", exact: true }).click();
  await page
    .getByRole("button", { name: "Confirm activation", exact: true })
    .click();
  await expect(
    page.getByRole("alert").filter({ hasText: "checksum failed" }),
  ).toBeVisible();
  await expect(
    page.getByText("Current: current-bundle", { exact: true }),
  ).toBeVisible();
  fail = false;
  await page.getByRole("button", { name: "Roll back", exact: true }).click();
  await page
    .getByRole("button", { name: "Confirm activation", exact: true })
    .click();
  await expect(
    page.getByText("Current: previous-bundle", { exact: true }),
  ).toBeVisible();
  expect(calls).toBe(2);
});
