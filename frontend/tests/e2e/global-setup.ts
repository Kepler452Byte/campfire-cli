import { chmod, readFile } from "node:fs/promises"
import { request } from "@playwright/test"

export default async function setup(): Promise<void> {
  let link = ""
  const deadline = Date.now() + 10000
  while (!link && Date.now() < deadline) {
    try {
      link = (JSON.parse(await readFile(".e2e-web.json", "utf8")) as { url: string }).url
    } catch { /* Web startup has not emitted its ready result. */ }
    if (!link) await new Promise(resolve => setTimeout(resolve, 50))
  }
  if (!link) throw new Error("Real Web startup did not complete")
  const url = new URL(link)
  const api = await request.newContext({ baseURL: url.origin })
  try {
    const result = await api.post("/api/session", {
      headers: { "Origin": url.origin, "X-Campfire-Request": "1" },
      data: { ticket: new URLSearchParams(url.hash.slice(1)).get("connect") }
    })
    if (!result.ok() || !(await api.get("/api/v1/environment")).ok()) throw new Error("Real session exchange failed")
    await api.storageState({ path: ".e2e-session.json" })
    await chmod(".e2e-session.json", 0o600)
  } finally {
    await api.dispose()
  }
}
