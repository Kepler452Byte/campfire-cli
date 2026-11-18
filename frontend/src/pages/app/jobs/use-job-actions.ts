import type { JobRow, Run } from "./types"
import { ElMessage, ElMessageBox } from "element-plus"
import { actOnJob } from "./api"
import "element-plus/es/components/message-box/style/css"

export function useJobActions(refresh: (run?: Run) => Promise<void>) {
  const busy = ref(false)
  async function execute(job: JobRow, action: string): Promise<void> {
    if (busy.value) return
    busy.value = true
    try {
      const plan = await actOnJob(job.id, action)
      const labels: Record<string, string> = { run: "立即执行", pause: "暂停", resume: "恢复", delete: "删除" }
      await ElMessageBox.confirm(
        `${labels[action]}「${job.name || job.id}」？工作区：${job.workspace_id || "未绑定"}。${action === "run" ? `超时 ${job.timeout} 秒。` : ""}`,
        "确认操作",
        { confirmButtonText: "确认", cancelButtonText: "取消", type: action === "delete" ? "warning" : "info" }
      )
      const result = await actOnJob(job.id, action, plan.expected_plan)
      ElMessage.success(action === "run" ? "已启动，可在日志页查看运行结果" : "操作已完成")
      await refresh(result.run)
    } catch {
      // 请求层报告业务错误；取消确认不发起写入。
    } finally {
      busy.value = false
    }
  }
  return { busy, execute }
}
