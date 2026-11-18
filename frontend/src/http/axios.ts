import type { AxiosRequestConfig } from "axios"
import axios from "axios"
import { ElMessage } from "element-plus"

interface Envelope<T> { code: number, message: string, data: T }
interface ErrorResult { message?: string, code?: string, write_performed?: boolean }
const client = axios.create({ baseURL: "/api/v1", timeout: 30000, headers: { "X-Campfire-Request": "1" } })

export async function establishSession(): Promise<void> {
  const ticket = new URLSearchParams(location.hash.slice(1)).get("connect")
  if (ticket) {
    history.replaceState(null, "", location.pathname + location.search)
    await client.post("/api/session", { ticket }, { baseURL: "" })
  }
  await client.get("/environment")
}

export async function request<T>(config: AxiosRequestConfig): Promise<T> {
  try {
    const response = await client.request<Envelope<T>>(config)
    if (response.data.code !== 0) throw new Error("响应契约错误")
    return response.data.data
  } catch (error: unknown) {
    const body = axios.isAxiosError<Envelope<ErrorResult>>(error) ? error.response?.data : undefined
    const message = axios.isAxiosError(error)
      ? body?.message || body?.data?.message || body?.data?.code || error.message
      : error instanceof Error ? error.message : "请求失败"
    ElMessage.error(body?.data?.write_performed ? `部分变更已写入，请核实当前状态。${message}` : message)
    throw error
  }
}
