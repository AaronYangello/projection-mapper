import { test, expect, type Page } from "@playwright/test";
let original: unknown;
let lease: string | undefined;
const navigation = (page: Page, name: string) =>
  page.getByRole("navigation").getByRole("button", { name, exact: true });
test.beforeAll(async ({ request }) => {
  original = (await (await request.get("/api/project")).json()).project;
});
test.beforeEach(async ({ page, request }) => {
  lease = undefined;
  await request.post("/api/runtime/stop");
  await request.post("/api/runtime/restore");
  await request.put("/api/pattern", { data: { pattern: "show" } });
  const { revision } = await (await request.get("/api/project")).json();
  expect(
    (
      await request.put("/api/project", {
        data: { revision, project: original },
      })
    ).ok(),
  ).toBeTruthy();
  page.on("response", async (response) => {
    if (
      response.url().endsWith("/api/mapping") &&
      response.request().method() === "POST" &&
      response.ok()
    )
      lease = (await response.json()).id;
  });
  await page.goto("/");
  await expect(navigation(page, "Playback")).toBeVisible();
});
test.afterEach(async ({ request }) => {
  if (lease) await request.delete(`/api/mapping/${lease}`);
});

for (const width of [1440, 768, 390])
  test(`all workspaces and navigation fit at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 768 ? 1024 : 900 });
    for (const name of [
      "Playback",
      "Show",
      "Mapping",
      "Media",
      "Project",
      "Diagnostics",
    ]) {
      const nav = navigation(page, name);
      await nav.click();
      await expect(
        page.getByRole("heading", { name, exact: true, level: 1 }),
      ).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBeTruthy();
      const box = await nav.boundingBox();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(width);
    }
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await navigation(page, "Playback").click();
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
  });

test("media selection is separate from playback; edits survive navigation and save", async ({
  page,
  request,
}) => {
  await navigation(page, "Media").click();
  await page.getByRole("button", { name: /^Sample image/ }).click();
  const name = page.getByRole("textbox", { name: "Display name", exact: true });
  await name.fill("Edited image");
  await navigation(page, "Playback").click();
  await navigation(page, "Media").click();
  await expect(name).toHaveValue("Edited image");
  await page.getByRole("button", { name: /^other/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Keep editing", exact: true }).click();
  expect((await (await request.get("/api/status")).json()).transport).toBe(
    "READY",
  );
  await page
    .getByRole("button", { name: "Save settings", exact: true })
    .click();
  await expect(
    page.getByText("Playback settings saved.", { exact: true }),
  ).toBeVisible();
  expect(
    (await (await request.get("/api/project")).json()).project.scenes.find(
      (s: { id: string }) => s.id === "sample",
    ).name,
  ).toBe("Edited image");
  await expect(
    page.getByRole("button", { name: "Save settings", exact: true }),
  ).toBeDisabled();
});

test("bulk add and shuffle file selection persist", async ({
  page,
  request,
}) => {
  await navigation(page, "Media").click();
  await page
    .getByRole("button", { name: /Add all playable files to show/ })
    .click();
  await expect(page.getByText("1 file added to the show.")).toBeVisible();
  await navigation(page, "Show").click();
  await page.getByRole("tab", { name: "Shuffle" }).click();
  await page.getByRole("radio", { name: "Choose files" }).check();
  await page.getByRole("checkbox", { name: "sample" }).uncheck();
  await page.getByRole("checkbox", { name: "clip" }).uncheck();
  await page.getByRole("button", { name: "Save shuffle media" }).click();
  await expect(
    page.getByRole("button", { name: "Save shuffle media" }),
  ).toBeDisabled();
  let show = (await (await request.get("/api/project")).json()).project.show;
  expect(show.shuffle_media_mode).toBe("selected");
  expect(show.shuffle_media_paths).toEqual(["media/other.png"]);
  await page.getByRole("radio", { name: "Shuffle all in folder" }).check();
  await page.getByRole("button", { name: "Save shuffle media" }).click();
  show = (await (await request.get("/api/project")).json()).project.show;
  expect(show.shuffle_media_mode).toBe("all_folder");
  expect(show.shuffle_media_paths).toEqual([]);
});

test("upload batch scans automatically and Media can delete its file", async ({
  page,
  request,
}) => {
  await navigation(page, "Media").click();
  await page
    .getByRole("region", { name: "Upload media" })
    .locator('input[type="file"]')
    .setInputFiles("../docs/screenshots/media.png");
  await expect(page.getByText(/Scan complete\. 5 files/)).toBeVisible();
  const assets = (await (await request.get("/api/media")).json()).assets;
  const uploaded = assets.find((a: { path: string }) =>
    a.path.endsWith("-media.png"),
  );
  expect(uploaded).toBeTruthy();
  await page.locator(".media-card").filter({ hasText: "media" }).last().click();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete file" }).click();
  await expect(
    page.getByText("media deleted from the media folder."),
  ).toBeVisible();
  expect(
    (await (await request.get("/api/media")).json()).assets.some(
      (a: { id: string }) => a.id === uploaded.id,
    ),
  ).toBe(false);
});

test("project draft survives another editor's save and cannot overwrite it", async ({
  page,
}) => {
  await navigation(page, "Project").click();
  const name = page.getByRole("textbox", { name: "Project name", exact: true });
  await name.fill("Unsaved project");
  await navigation(page, "Media").click();
  await page.getByRole("button", { name: /^Sample image/ }).click();
  await page
    .getByRole("textbox", { name: "Display name", exact: true })
    .fill("Saved elsewhere");
  await page
    .getByRole("button", { name: "Save settings", exact: true })
    .click();
  await expect(
    page.getByText("Playback settings saved.", { exact: true }),
  ).toBeVisible();
  await navigation(page, "Project").click();
  await expect(name).toHaveValue("Unsaved project");
  await expect(
    page.getByText("The project changed while you were editing.", {
      exact: false,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Save & apply project", exact: true }),
  ).toBeDisabled();
});

test("mapping nudge, undo, redo, leave protection and durable save", async ({
  page,
  request,
}) => {
  const before = (await (await request.get("/api/project")).json()).project
    .surfaces[0].mapping.top_left[0];
  await navigation(page, "Mapping").click();
  const save = page.getByRole("button", { name: "Save mapping", exact: true });
  await expect(save).toBeDisabled();
  expect(
    (await (await request.get("/api/status")).json()).calibration,
  ).toBeNull();
  await page.getByRole("button", { name: "Nudge right", exact: true }).click();
  await expect(save).toBeEnabled();
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  // Save can also finish a live preview whose geometry was undone.
  await expect(save).toBeEnabled();
  await page.getByRole("button", { name: "Redo", exact: true }).click();
  await expect(save).toBeEnabled();
  await navigation(page, "Media").click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Keep editing", exact: true }).click();
  await save.click();
  await expect(page.locator(".mapping-ack")).toHaveText(/Mapping saved/);
  const after = (await (await request.get("/api/project")).json()).project
    .surfaces[0].mapping.top_left[0];
  expect(after).toBeGreaterThan(before);
  await expect(save).toBeDisabled();
  expect(
    (await (await request.get("/api/status")).json()).calibration,
  ).toBeNull();
  await expect(
    page.getByRole("combobox", { name: "Surface", exact: true }),
  ).toBeEnabled();
});

test("first drag survives a slow lease and Save flushes the final corner", async ({
  page,
  request,
}) => {
  await navigation(page, "Mapping").click();
  let starts = 0;
  await page.route("**/api/mapping", async (route) => {
    starts++;
    await new Promise((resolve) => setTimeout(resolve, 450));
    await route.continue();
  });
  const handle = page.getByRole("button", {
    name: "Move top left corner",
    exact: true,
  });
  const box = (await handle.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(
    box.x + box.width / 2 + 14,
    box.y + box.height / 2 + 12,
    { steps: 5 },
  );
  await page.mouse.up();
  const position = await handle.getAttribute("style");
  await page.getByRole("button", { name: "Save mapping", exact: true }).click();
  await expect(page.locator(".mapping-ack")).toContainText("Mapping saved");
  expect(await handle.getAttribute("style")).toBe(position);
  expect(starts).toBe(1);
  expect(
    (await (await request.get("/api/status")).json()).calibration,
  ).toBeNull();
});

test("Revert during lease opening preserves saved geometry and restores content", async ({
  page,
  request,
}) => {
  const before = (await (await request.get("/api/project")).json()).project;
  await navigation(page, "Mapping").click();
  await page.route("**/api/mapping", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 350));
    await route.continue();
  });
  await page.getByRole("button", { name: "Nudge right", exact: true }).click();
  await page.getByRole("button", { name: "Revert", exact: true }).click();
  await expect(page.locator(".mapping-ack")).toContainText("Mapping reverted");
  expect((await (await request.get("/api/project")).json()).project).toEqual(
    before,
  );
  expect(
    (await (await request.get("/api/status")).json()).calibration,
  ).toBeNull();
});

test("Save also ends preview when a running older server ignores finish", async ({
  page,
  request,
}) => {
  await page.route("**/api/mapping/*/save?finish=true", (route) =>
    route.continue({
      url: route.request().url().replace("finish=true", "finish=false"),
    }),
  );
  await navigation(page, "Mapping").click();
  await page.getByRole("button", { name: "Nudge right", exact: true }).click();
  await page.getByRole("button", { name: "Save mapping", exact: true }).click();
  await expect(page.locator(".mapping-ack")).toContainText("Mapping saved");
  expect(
    (await (await request.get("/api/status")).json()).calibration,
  ).toBeNull();
});

test("discarding mapping on navigation releases the lease", async ({
  page,
  request,
}) => {
  await navigation(page, "Mapping").click();
  await page.getByRole("button", { name: "Nudge right", exact: true }).click();
  await navigation(page, "Media").click();
  await page
    .getByRole("button", { name: "Discard changes", exact: true })
    .click();
  await expect(navigation(page, "Media")).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expect
    .poll(
      async () => (await (await request.get("/api/status")).json()).calibration,
    )
    .toBeNull();
});

test("blackout explains frozen playback and test patterns have an exit everywhere", async ({
  page,
  request,
}) => {
  await page.getByRole("button", { name: "Start show", exact: true }).click();
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await page.getByRole("button", { name: "Blackout", exact: true }).click();
  await expect(
    page.getByText("Blackout active.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Resume", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Restore output", exact: true })
    .click();
  expect((await (await request.get("/api/status")).json()).transport).toBe(
    "PAUSED",
  );
  await navigation(page, "Diagnostics").click();
  await page.getByRole("button", { name: "Grid", exact: true }).click();
  await navigation(page, "Media").click();
  await page
    .getByRole("button", { name: "Return to content", exact: true })
    .click();
  await expect
    .poll(async () => (await (await request.get("/api/status")).json()).pattern)
    .toBe("show");
});

test("library filters, empty result recovery and readable file errors", async ({
  page,
}) => {
  await navigation(page, "Media").click();
  const issues = page.getByRole("region", { name: "Media issues" });
  await expect(issues).toBeVisible();
  await expect(issues).toContainText("broken.mp4");
  await expect(
    page.getByText("Technical details", { exact: true }),
  ).toHaveCount(0);
  const search = page.getByRole("searchbox");
  await search.fill("nothing-matches-this");
  await expect(
    page.getByText("No files match these filters.", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Clear filters", exact: true })
    .click();
  await expect(search).toHaveValue("");
  await page
    .getByRole("combobox", { name: "File type", exact: true })
    .selectOption("attention");
  await expect(page.locator(".media-card")).toHaveCount(1);
  await page.getByRole("button", { name: /^broken/ }).click();
  await expect(issues).toBeVisible();
  await expect(
    page.locator(".media-card.has-error .media-attention"),
  ).toBeVisible();
});

test("media issue details replace duplicate banners but preserve clip warnings", async ({
  page,
  request,
}) => {
  const data = await (await request.get("/api/project")).json();
  data.project.scenes.push({
    id: "missing",
    name: "Missing source",
    type: "video",
    path: "media/missing.mp4",
  });
  data.project.scenes.find(
    (s: { id: string }) => s.id === "clip",
  ).start_seconds = 10;
  expect((await request.put("/api/project", { data })).ok()).toBeTruthy();
  await page.reload();
  await navigation(page, "Media").click();
  await page.getByRole("button", { name: "Scan folder", exact: true }).click();
  const issues = page.getByRole("region", { name: "Media issues" });
  await expect(issues).toContainText("Missing source");
  await expect(issues).toContainText("Media file is missing");
  await expect(page.locator(".notice.warning")).toContainText(
    "Clip starts after the video ends",
  );
  await expect(page.locator(".notice.warning")).not.toContainText(
    "Missing source",
  );
  await navigation(page, "Playback").click();
  await expect(page.locator(".notice.warning")).toContainText("Missing source");
});

test("common topology edits save without JSON", async ({ page, request }) => {
  await navigation(page, "Project").click();
  await page.getByText(/^Projectors ·/).click();
  await page
    .getByRole("textbox", { name: "Projector name", exact: true })
    .first()
    .fill("Front wall");
  await page
    .getByRole("button", { name: "Save & apply project", exact: true })
    .click();
  await expect(
    page.getByText("Project saved and applied.", { exact: true }),
  ).toBeVisible();
  expect(
    (await (await request.get("/api/project")).json()).project.projectors[0]
      .name,
  ).toBe("Front wall");
  await expect(
    page.getByRole("button", { name: "Save & apply project", exact: true }),
  ).toBeDisabled();
});

test("one-projector and one-surface shortcuts stop and save without deleting mappings", async ({
  page,
  request,
}) => {
  const originalProject = (await (await request.get("/api/project")).json())
    .project;
  const firstProjector = originalProject.projectors[0];
  const secondSurface = originalProject.surfaces.find(
    (s: { projector_id: string }) => s.projector_id !== firstProjector.id,
  );
  await request.post("/api/runtime/start");
  await navigation(page, "Project").click();
  await page.getByText(/^Projectors ·/).click();
  await page
    .getByRole("button", { name: `Only ${firstProjector.name}` })
    .click();
  const stopAndSave = page.getByRole("button", {
    name: "Stop show & save project",
  });
  await expect(stopAndSave).toBeEnabled();
  await stopAndSave.click();
  await expect(page.getByText("Project saved and applied.")).toBeVisible();
  expect((await (await request.get("/api/status")).json()).transport).toBe(
    "READY",
  );
  let saved = (await (await request.get("/api/project")).json()).project;
  expect(
    saved.projectors.filter((p: { enabled: boolean }) => p.enabled),
  ).toHaveLength(1);
  expect(saved.surfaces).toHaveLength(originalProject.surfaces.length);

  await page.getByText(/^Surfaces ·/).click();
  await page
    .getByRole("button", { name: `Only ${secondSurface.name}` })
    .click();
  await page.getByRole("button", { name: "Save & apply project" }).click();
  saved = (await (await request.get("/api/project")).json()).project;
  expect(
    saved.surfaces.filter((s: { enabled: boolean }) => s.enabled),
  ).toHaveLength(1);
  expect(
    saved.surfaces.find((s: { id: string }) => s.id === secondSurface.id)
      .enabled,
  ).toBe(true);
  expect(
    saved.projectors.find(
      (p: { id: string }) => p.id === secondSurface.projector_id,
    ).enabled,
  ).toBe(true);
  expect(saved.surfaces).toHaveLength(originalProject.surfaces.length);
});

test("Space controls playback but never fires while editing a field", async ({
  page,
  request,
}) => {
  await page.evaluate(() => {
    if (document.activeElement instanceof HTMLElement)
      document.activeElement.blur();
  });
  await page.keyboard.press("Space");
  await expect
    .poll(
      async () => (await (await request.get("/api/status")).json()).transport,
    )
    .toBe("RUNNING");
  await expect(
    page.getByRole("button", { name: "Pause", exact: true }),
  ).toBeEnabled();
  await page.keyboard.press("Space");
  await expect
    .poll(
      async () => (await (await request.get("/api/status")).json()).transport,
    )
    .toBe("PAUSED");
  await navigation(page, "Project").click();
  const name = page.getByRole("textbox", { name: "Project name", exact: true });
  await name.fill("Keyboard test");
  await name.press("Space");
  expect((await (await request.get("/api/status")).json()).transport).toBe(
    "PAUSED",
  );
});
