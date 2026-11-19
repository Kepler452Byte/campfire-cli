import axios from "axios"
import { shallowRef } from "vue"
import { client } from "./client"

export type ConnectionState = "connecting" | "ready" | "session-required" | "invalid-ticket" | "unreachable" | "initialization-error"
export const connection = shallowRef<ConnectionState>("connecting")
let pending: Promise<void> | undefined

export function takeConnectionTicket(): string | undefined {
  const params = new URLSearchParams(location.hash.slice(1))
  const ticket = params.get("connect") || undefined
  if (params.has("connect")) history.replaceState(null, "", location.pathname + location.search)
  return ticket
}

// Remove credentials before router history or tag persistence observes the URL.
export const initialTicket = takeConnectionTicket()

export function ticketFromLink(value: string): string {
  const url = new URL(value.trim())
  const ticket = new URLSearchParams(url.hash.slice(1)).get("connect")
  if (!["http:", "https:"].includes(url.protocol) || !ticket) throw new Error("请输入 CLI 输出的完整连接链接")
  return ticket
}

function errorCode(error: unknown): string | undefined {
  return axios.isAxiosError<{ data?: { code?: string } }>(error) ? error.response?.data?.data?.code : undefined
}
function failure(error: unknown): ConnectionState {
  if (errorCode(error) === "invalid-ticket") return "invalid-ticket"
  if (errorCode(error) === "session-required") return "session-required"
  if (axios.isAxiosError(error) && !error.response) return "unreachable"
  return "initialization-error"
}

async function authenticate(ticket?: string): Promise<void> {
  let ticketError: unknown
  if (ticket) {
    try {
      await client.post("/api/session", { ticket }, { baseURL: "" })
    } catch (error) {
      if (errorCode(error) !== "invalid-ticket") throw error
      ticketError = error
    }
  }
  try {
    const result = await client.get("/environment")
    if (result.data.code !== 0 || result.data.data?.status !== "ok") throw new Error("Invalid environment response")
  } catch (error) {
    throw ticketError && errorCode(error) === "session-required" ? ticketError : error
  }
}

export function connect(ticket?: string): Promise<void> {
  if (pending) return pending
  connection.value = "connecting"
  pending = authenticate(ticket).then(() => {
    connection.value = "ready"
  }).catch((error: unknown) => {
    connection.value = failure(error)
  }).finally(() => {
    pending = undefined
  })
  return pending
}

client.interceptors.response.use(response => response, (error: unknown) => {
  if (connection.value === "ready" && !axios.isCancel(error)) {
    const state = failure(error)
    if (state === "session-required" || state === "unreachable") connection.value = state
  }
  return Promise.reject(error)
})
