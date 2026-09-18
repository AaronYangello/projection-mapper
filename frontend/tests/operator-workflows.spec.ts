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
  await page
    .getByRole("button", { name: "Start mapping", exact: true })
    .click();
  const save = page.getByRole("button", { name: "Save mapping", exact: true });
  await page.getByRole("button", { name: "Nudge right", exact: true }).click();
  await expect(save).toBeEnabled();
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(save).toBeDisabled();
  await page.getByRole("button", { name: "Redo", exact: true }).click();
  await expect(save).toBeEnabled();
  await navigation(page, "Media").click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Keep editing", exact: true }).click();
  await save.click();
  await expect(page.getByText("Mapping saved", { exact: true })).toBeVisible();
  const after = (await (await request.get("/api/project")).json()).project
    .surfaces[0].mapping.top_left[0];
  expect(after).toBeGreaterThan(before);
  await page
    .getByRole("button", { name: "Finish mapping", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Start mapping", exact: true }),
  ).toBeVisible();
});

test("discarding mapping on navigation releases the lease", async ({
  page,
  request,
}) => {
  await navigation(page, "Mapping").click();
  await page
    .getByRole("button", { name: "Start mapping", exact: true })
    .click();
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
  await expect(
    page.getByText("Fix or replace the file, then scan again.", {
      exact: false,
    }),
  ).toBeVisible();
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
