import type { Environment, Job, JobRow, LogChunk, Page, Plan, Run } from "./types"
import { request } from "@/http/axios"

export const getEnvironment = () => request<{ environment: Environment, version: string }>({ url: "/environment" })
export const getWorkspaces = () => request<{ workspaces: Record<string, { path: string }> }>({ url: "/workspaces" })
export const listJobs = (params: Record<string, unknown>) => request<Page<JobRow>>({ url: "/jobs", params })
export const getJob = (id: string, notifyError = true) => request<{ job: JobRow }>({ url: `/jobs/${encodeURIComponent(id)}` }, notifyError)
export function saveJob(job: Job, edit: boolean, expected?: string) {
  return request<Plan>({
    url: edit ? `/jobs/${encodeURIComponent(job.id)}` : "/jobs",
    method: edit ? "PUT" : "POST",
    data: { job, confirm: !!expected, expected_plan: expected }
  })
}
export function actOnJob(id: string, action: string, expected?: string) {
  return request<Plan>({
    url: `/jobs/${encodeURIComponent(id)}/${action}`,
    method: "POST",
    data: { confirm: !!expected, expected_plan: expected }
  })
}
export function listRuns(id: string, page: number, pageSize: number) {
  return request<Page<Run>>({
    url: `/jobs/${encodeURIComponent(id)}/runs`,
    params: { page, page_size: pageSize }
  })
}
export function listAllRuns(page: number, pageSize: number, jobId?: string) {
  return request<Page<Run>>({ url: "/runs", params: { page, page_size: pageSize, job_id: jobId || undefined } })
}
export const getRun = (id: string) => request<{ run: Run }>({ url: `/runs/${encodeURIComponent(id)}` })
export function getLogs(id: string, after: number) {
  return request<{ chunks: LogChunk[], next_cursor: number, truncated: boolean }>({
    url: `/runs/${encodeURIComponent(id)}/logs`,
    params: { after, limit: 100 }
  })
}
