import type { AxiosRequestConfig } from "axios"
import axios from "axios"
import { ElMessage } from "element-plus"
import { client } from "./client"

interface Envelope<T> { code: number, message: string, data: T }
interface ErrorResult { message?: string, code?: string, write_performed?: boolean }
export async function request<T>(config: AxiosRequestConfig, notifyError = true): Promise<T> {
  try {
    const response = await client.request<Envelope<T>>(config)
    if (response.data.code !== 0) throw new Error("响应契约错误")
    return response.data.data
  } catch (error: unknown) {
    const body = axios.isAxiosError<Envelope<ErrorResult>>(error) ? error.response?.data : undefined
    const message = axios.isAxiosError(error)
      ? body?.message || body?.data?.message || body?.data?.code || error.message
      : error instanceof Error ? error.message : "请求失败"
    if (notifyError) ElMessage.error(body?.data?.write_performed ? `部分变更已写入，请核实当前状态。${message}` : message)
    throw error
  }
}
