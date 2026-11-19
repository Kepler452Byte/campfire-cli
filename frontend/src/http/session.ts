import { client } from "./client"

export async function establishSession(): Promise<void> {
  const ticket = new URLSearchParams(location.hash.slice(1)).get("connect")
  if (ticket) {
    history.replaceState(null, "", location.pathname + location.search)
    await client.post("/api/session", { ticket }, { baseURL: "" })
  }
  await client.get("/environment")
}
