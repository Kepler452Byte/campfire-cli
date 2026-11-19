import path from "node:path"
import { defineConfig } from "@playwright/test"

const python = process.env.E2E_PYTHON || path.resolve("..", ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python")
export default defineConfig({
  globalSetup: "./tests/e2e/global-setup.ts",
  testDir: "tests/e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  use: { baseURL: "http://127.0.0.1:4173", storageState: ".e2e-session.json", headless: true },
  webServer: { command: `"${python}" tests/e2e/start-server.py`, url: "http://127.0.0.1:4173", reuseExistingServer: false }
})
