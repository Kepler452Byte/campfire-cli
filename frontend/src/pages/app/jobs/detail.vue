<script setup lang="ts">
import type { JobRow, Run } from "./types"
import { useList } from "@@/composables/use-list"
import { useTagsViewStore } from "@/pinia/stores/tags-view"
import { getEnvironment, getJob, listRuns } from "./api"
import JobEditor from "./components/JobEditor.vue"
import { runLabels, scheduleLabel, startedLabel } from "./types"
import { useJobActions } from "./use-job-actions"

const route = useRoute()
const router = useRouter()
const identity = String(route.params.id)
const pagePath = route.path
const tags = useTagsViewStore()
const job = ref<JobRow>()
const timezone = ref("")
const failed = ref(false)
const editor = ref(false)
const tab = ref("history")
const history = useList<Run>((page, size) => listRuns(identity, page, size))
const { rows, pager, loading, failed: historyFailed } = history
async function refresh(): Promise<void> {
  failed.value = false
  try {
    job.value = (await getJob(identity)).job
    tags.setVisitedTitle(pagePath, job.value.name || job.value.id)
  } catch {
    failed.value = true
  }
}
const actions = useJobActions(async (run?: Run) => {
  if (run) {
    await router.push(`/app/jobs/${identity}/runs/${run.id}`)
    return
  }
  await Promise.all([refresh(), history.load()])
})
onMounted(async () => {
  await refresh()
  try {
    timezone.value = (await getEnvironment()).environment.timezone
  } catch {
    // 请求层报告环境查询失败，任务详情仍可阅读。
  }
})
const refreshTimer = setInterval(() => {
  if (!document.hidden && !editor.value && !loading.value && !historyFailed.value && !failed.value) {
    void Promise.all([refresh(), history.load()])
  }
}, 5000)
onScopeDispose(() => clearInterval(refreshTimer))

async function saved(): Promise<void> {
  editor.value = false
  await refresh()
}
</script>

<template>
  <div class="job-detail">
    <el-alert v-if="failed" title="任务读取失败，请重试" type="error" :closable="false">
      <el-button link @click="refresh">
        重试
      </el-button>
    </el-alert>
    <template v-else-if="job">
      <div class="three-line-table-wrap job-summary-wrap">
        <table class="three-line-table job-summary" aria-label="任务概览">
          <thead>
            <tr>
              <th scope="col">
                任务
              </th>
              <th scope="col">
                状态
              </th>
              <th scope="col">
                操作
              </th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>{{ job.name || job.id }}</td>
              <td>
                <el-tag :type="job.scheduler.enabled ? 'success' : 'info'">
                  {{ job.schedule.kind === 'manual' ? '仅手动' : job.scheduler.enabled ? '已启用' : '已暂停' }}
                </el-tag>
              </td>
              <td>
                <div class="detail-actions">
                  <el-button :disabled="actions.busy.value" @click="actions.execute(job, 'run')">
                    立即执行
                  </el-button><el-button v-if="job.schedule.kind !== 'manual'" :disabled="actions.busy.value" @click="actions.execute(job, job.scheduler.enabled ? 'pause' : 'resume')">
                    {{ job.scheduler.enabled ? '暂停' : '恢复' }}
                  </el-button><el-button v-if="job.script_project" @click="router.push(`/app/scripts/${encodeURIComponent(job.script_project)}`)">
                    查看脚本
                  </el-button><el-button @click="editor = true">
                    编辑
                  </el-button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <el-tabs v-model="tab">
        <el-tab-pane label="运行历史" name="history">
          <el-table :data="rows" row-key="id">
            <template #empty>
              <el-button v-if="historyFailed" link @click="history.load">
                加载失败，请重试
              </el-button><span v-else>暂无运行记录</span>
            </template>
            <el-table-column label="开始时间" min-width="200">
              <template #default="{ row }">
                {{ startedLabel(row) }}
              </template>
            </el-table-column>
            <el-table-column label="耗时" width="100">
              <template #default="{ row }">
                {{ row.duration == null ? '—' : `${row.duration.toFixed(1)}秒` }}
              </template>
            </el-table-column>
            <el-table-column label="进程结果" width="110">
              <template #default="{ row }">
                {{ runLabels[row.status as Run['status']] }}
              </template>
            </el-table-column>
            <el-table-column prop="exit_code" label="退出码" width="90">
              <template #default="{ row }">
                {{ row.exit_code ?? '—' }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="router.push(`/app/jobs/${identity}/runs/${row.id}`)">
                  查看日志
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="admin-pager history-pager">
            <el-pagination :total="pager.total" :page-size="pager.pageSize" :current-page="pager.currentPage" layout="total, prev, pager, next" @current-change="history.changePage" />
          </div>
        </el-tab-pane>
        <el-tab-pane label="任务配置" name="configuration">
          <el-descriptions class="job-configuration" :column="1" label-width="112px" border>
            <el-descriptions-item label="任务 ID">
              {{ job.id }}
            </el-descriptions-item>
            <el-descriptions-item label="工作区">
              {{ job.workspace_id || '未绑定' }}
            </el-descriptions-item>
            <el-descriptions-item label="执行计划">
              {{ scheduleLabel(job.schedule) }}
            </el-descriptions-item>
            <el-descriptions-item label="执行时区">
              {{ timezone }}
            </el-descriptions-item>
            <el-descriptions-item label="启用状态">
              {{ job.schedule.kind === 'manual' ? '不适用' : job.scheduler.enabled ? '已启用' : '已暂停' }}
            </el-descriptions-item>
            <el-descriptions-item v-if="job.script_project" label="脚本项目">
              <el-button link type="primary" @click="router.push(`/app/scripts/${encodeURIComponent(job.script_project)}`)">
                {{ job.script_project }}
              </el-button>
            </el-descriptions-item>
            <el-descriptions-item label="工作目录">
              {{ job.cwd }}
            </el-descriptions-item>
            <el-descriptions-item label="超时">
              {{ job.timeout }} 秒
            </el-descriptions-item>
            <el-descriptions-item label="程序">
              {{ job.argv[0] }}
            </el-descriptions-item>
            <el-descriptions-item label="参数">
              <pre>{{ JSON.stringify(job.argv.slice(1), null, 2) }}</pre>
            </el-descriptions-item>
          </el-descriptions>
        </el-tab-pane>
      </el-tabs>
      <JobEditor v-if="editor" :job="job" :timezone="timezone" @close="editor = false" @saved="saved" />
    </template>
  </div>
</template>

<style scoped lang="scss">
.job-detail {
  padding: 20px;
  min-width: 0;
}
.job-summary-wrap {
  margin-bottom: 20px;
}
.job-summary {
  min-width: 0;
  td:first-child {
    white-space: normal;
    overflow-wrap: anywhere;
  }
}
.detail-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  .el-button {
    margin-left: 0;
  }
}
@media (min-width: 769px) {
  .detail-actions {
    flex-wrap: nowrap;
  }
}
.history-pager {
  margin: 16px 0;
}
.job-configuration {
  :deep(.el-descriptions__table) {
    table-layout: fixed;
  }
  :deep(.el-descriptions__label) {
    white-space: nowrap;
  }
  :deep(.el-descriptions__content) {
    overflow-wrap: anywhere;
  }
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  margin: 0;
}
</style>
