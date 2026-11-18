export interface Schedule {
  kind: "manual" | "interval" | "daily" | "weekly"
  seconds?: number
  time?: string
  day?: string
}
export interface Agent {
  kind: "codex" | "claude"
  executable: string
  args: string[]
  prompt: string
}
export interface Job {
  id: string
  name: string | null
  argv?: string[]
  agent?: Agent
  cwd: string
  timeout: number
  workspace_id: string | null
  workspace_root?: string | null
  script_project?: string | null
  schedule: Schedule
}
export interface Run {
  id: string
  job_id: string
  status: "running" | "succeeded" | "failed" | "timeout" | "interrupted"
  started: string
  duration: number | null
  exit_code: number | null
  truncated: number
  display_time?: { started: string, finished: string | null }
}
export interface JobRow extends Job {
  scheduler: { enabled: boolean, deployed: boolean }
  latest_run: Run | null
}
export interface Page<T> { list: T[], total: number, page: number, page_size: number, pages: number }
export interface Plan {
  status: string
  expected_plan: string
  write_performed: boolean
  before?: Job | null
  after?: Job | null
  job?: Job
  action?: string
  enabled_after?: boolean
  run?: Run
}
export interface Environment { name: string, id: string | null, timezone: string, platform: string }
export interface LogChunk { seq: number, stream: "stdout" | "stderr", content: string }

export const runLabels: Record<Run["status"], string> = {
  running: "运行中",
  succeeded: "进程成功",
  failed: "进程失败",
  timeout: "超时",
  interrupted: "中断"
}
export function startedLabel(run: Run): string {
  return (run.display_time?.started || run.started).slice(0, 19).replace("T", " ")
}
export function scheduleLabel(schedule: Schedule): string {
  if (schedule.kind === "manual") return "仅手动"
  if (schedule.kind === "interval") return `每 ${(schedule.seconds ?? 60) / 60} 分钟`
  if (schedule.kind === "daily") return `每天 ${schedule.time}`
  const days: Record<string, string> = { mon: "一", tue: "二", wed: "三", thu: "四", fri: "五", sat: "六", sun: "日" }
  return `每周${days[schedule.day ?? "mon"]} ${schedule.time}`
}
