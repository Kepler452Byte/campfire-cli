import { execFile } from "node:child_process"
import { readFile } from "node:fs/promises"
import path from "node:path"
import { promisify } from "node:util"
import { expect, test } from "@playwright/test"

const execute = promisify(execFile)
const python = process.env.E2E_PYTHON || path.resolve("..", ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python")
test.use({ storageState: { cookies: [], origins: [] } })
async function home(): Promise<string> {
  return (JSON.parse(await readFile(".e2e-home.json", "utf8")) as { home: string }).home
}
async function link(): Promise<string> {
  const result = await execute(python, ["-m", "campfire_cli.main", "web", "--no-open"], { env: { ...process.env, CAMPFIRE_HOME: await home() } })
  const response = JSON.parse(result.stdout) as { status: string, action: string, url: string }
  expect(response.action).toBe("reconnected")
  return response.url
}
function at(link: string, target: string): string {
  const url = new URL(target, link)
  url.hash = new URL(link).hash
  return url.toString()
}

test("无 Cookie 的深层页面通过真实 CLI 票据恢复，保留路径", async ({ page }) => {
  const target = "/app/scripts?project=growth&file=helpers%2Fstudy.py"
  await page.goto(target)
  const recovery = page.getByRole("main")
  await expect(recovery.getByRole("heading", { name: "需要重新连接" })).toBeVisible()
  await expect(recovery).toContainText("campfire web --no-open")
  await expect(page).toHaveURL(/\/app\/scripts\?project=growth&file=helpers%2Fstudy.py$/)
  await page.screenshot({ path: "test-results/session-required.png", fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  await page.screenshot({ path: "test-results/session-required-mobile.png", fullPage: true })
  await recovery.getByRole("textbox", { name: "新的连接链接" }).fill(await link())
  await recovery.getByRole("button", { name: "连接", exact: true }).click()
  await expect(page.getByLabel("源码 helpers/study.py", { exact: true })).toContainText("学习记录")
  expect((await page.request.get("/api/v1/environment")).ok()).toBe(true)
  expect(new URL(page.url()).search).toBe("?project=growth&file=helpers%2Fstudy.py")
})

test("使用过的链接接受有效 Cookie，Cookie 丢失后明确恢复且票据不进入标签缓存", async ({ page, context }) => {
  const current = await link()
  const ticket = new URL(current).hash.slice("#connect=".length)
  const target = at(current, "/app/scripts?project=growth&file=daily.py")
  await page.goto(target)
  await expect(page.getByLabel("源码 daily.py", { exact: true })).toBeVisible()
  expect(new URL(page.url()).hash).toBe("")
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain(ticket)
  await page.goto("about:blank")
  await page.goto(target)
  await expect(page.getByLabel("源码 daily.py", { exact: true })).toBeVisible()
  expect((await page.request.get("/api/v1/environment")).ok()).toBe(true)
  await context.clearCookies()
  await page.goto("about:blank")
  await page.goto(target)
  await expect(page.getByRole("heading", { name: "连接链接已失效" })).toBeVisible()
  await page.getByRole("textbox", { name: "新的连接链接" }).fill(await link())
  await page.getByRole("button", { name: "连接", exact: true }).click()
  await expect(page.getByLabel("源码 daily.py", { exact: true })).toBeVisible()
})

test("区分服务不可达、初始化异常和会话失效", async ({ page }) => {
  await page.route("**/api/v1/environment", route => route.abort())
  await page.goto("/app/scripts")
  await expect(page.getByRole("heading", { name: "暂时无法连接服务" })).toBeVisible()
  await page.unroute("**/api/v1/environment")
  await page.route("**/api/v1/environment", route => route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ code: 500, data: { code: "internal-error" } }) }))
  await page.getByRole("button", { name: "重试连接" }).click()
  await expect(page.getByRole("heading", { name: "页面初始化失败" })).toBeVisible()
  await page.unroute("**/api/v1/environment")
  await page.getByRole("button", { name: "重新加载" }).click()
  await expect(page.getByRole("heading", { name: "需要重新连接" })).toBeVisible()
})

test("真实服务同端口重启，失效的写请求不会在恢复后重放", async ({ page }) => {
  await page.goto(at(await link(), "/app/jobs/seed"))
  const summary = page.getByRole("table", { name: "任务概览", exact: true })
  await expect(summary).toContainText("预置任务")
  await page.getByRole("button", { name: "编辑", exact: true }).click()
  const dialog = page.getByRole("dialog")
  await dialog.getByRole("textbox", { name: "名称", exact: true }).fill("不得自动保存")
  await dialog.getByRole("button", { name: "预览变更", exact: true }).click()
  await expect(dialog.getByRole("button", { name: "确认保存", exact: true })).toBeVisible()
  const file = path.join(await home(), "web.json")
  const old = JSON.parse(await readFile(file, "utf8")) as { pid: number }
  process.kill(old.pid)
  await expect.poll(async () => {
    try {
      return (JSON.parse(await readFile(file, "utf8")) as { pid: number }).pid
    } catch {
      return old.pid
    }
  }).not.toBe(old.pid)
  let writes = 0
  page.on("request", (request) => {
    if (request.method() === "PUT" && new URL(request.url()).pathname === "/api/v1/jobs/seed") writes++
  })
  await dialog.getByRole("button", { name: "确认保存", exact: true }).click()
  await expect(page.getByRole("heading", { name: "需要重新连接" })).toBeVisible()
  expect(writes).toBe(1)
  expect((await page.request.get("/api/v1/environment")).status()).toBe(401)
  await page.reload()
  await expect(page.getByRole("heading", { name: "需要重新连接" })).toBeVisible()
  await page.getByRole("textbox", { name: "新的连接链接" }).fill(await link())
  await page.getByRole("button", { name: "连接", exact: true }).click()
  await expect(summary).toContainText("预置任务")
  expect(writes).toBe(1)
  const job = (await (await page.request.get("/api/v1/jobs/seed")).json()).data.job
  expect(job.name).toBe("预置任务")
  expect((await page.request.get("/api/v1/environment")).ok()).toBe(true)
})
