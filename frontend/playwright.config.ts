import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8012",
    headless: true,
    channel: "chrome",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "../.venv/bin/python ../scripts/serve_ux_fixture.py",
    url: "http://127.0.0.1:8012/api/status",
    reuseExistingServer: false,
    timeout: 30000,
  },
});
