<script setup lang="ts">
import type { Job, JobRow, Run } from "./types"
import { useList } from "@@/composables/use-list"
import { getEnvironment, getJob, getWorkspaces, listJobs } from "./api"
import JobEditor from "./components/JobEditor.vue"
import { runLabels, scheduleLabel } from "./types"
import { useJobActions } from "./use-job-actions"

const router = useRouter()
const filters = ref({ name: "", workspace_id: "", state: "" })
const workspaces = ref<string[]>([])
const timezone = ref("")
const editor = ref(false)
const editing = ref<Job>()
const list = useList<JobRow>((page, page_size) => {
  const params: Record<string, unknown> = { name: filters.value.name, state: filters.value.state || undefined, page, page_size }
  if (filters.value.workspace_id === "unbound") params.unbound = true
  else if (filters.value.workspace_id) params.workspace_id = filters.value.workspace_id.slice("workspace:".length)
  return listJobs(params)
})
const { pager, rows, loading, failed } = list
const actions = useJobActions(async (run?: Run) => {
  if (run) await router.push(`/app/jobs/${run.job_id}/runs/${run.id}`)
  else await list.load()
})
onMounted(async () => {
  try {
    const [registry, environment] = await Promise.all([getWorkspaces(), getEnvironment()])
    workspaces.value = Object.keys(registry.workspaces)
    timezone.value = environment.environment.timezone
  } catch {
    // 请求层报告元数据加载失败，任务查询独立保留结果。
  }
})
const refreshTimer = setInterval(() => {
  if (!document.hidden && !editor.value && !loading.value && !failed.value && !actions.busy.value) void list.load()
}, 5000)
onScopeDispose(() => clearInterval(refreshTimer))

function reset(): void {
  filters.value = { name: "", workspace_id: "", state: "" }
  void list.search()
}
async function edit(row?: JobRow): Promise<void> {
  editing.value = row ? (await getJob(row.id)).job : undefined
  editor.value = true
}
async function saved(): Promise<void> {
  editor.value = false
  await list.load()
}
</script>

<template>
  <div class="admin-page">
    <el-card class="admin-search" shadow="never">
      <el-form inline class="admin-search__form" @submit.prevent="list.search">
        <el-form-item label="名称">
          <el-input v-model="filters.name" clearable aria-label="搜索名称" @clear="list.search" />
        </el-form-item>
        <el-form-item label="工作区">
          <el-select v-model="filters.workspace_id" placeholder="全部" aria-label="筛选工作区" @change="list.search">
            <el-option label="全部" value="" /><el-option label="未绑定" value="unbound" /><el-option v-for="id in workspaces" :key="id" :label="id" :value="`workspace:${id}`" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.state" placeholder="全部" aria-label="筛选状态" @change="list.search">
            <el-option label="全部" value="" /><el-option label="已启用" value="enabled" /><el-option label="已暂停" value="paused" /><el-option label="仅手动" value="manual" />
          </el-select>
        </el-form-item>
        <el-form-item class="admin-search__actions">
          <el-button type="primary" @click="edit()">
            新增
          </el-button><el-button native-type="submit">
            查询
          </el-button><el-button @click="reset">
            重置
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
    <el-card class="admin-table" shadow="never">
      <div class="admin-table__body">
        <el-table :data="rows" row-key="id" height="100%">
          <template #empty>
            <el-button v-if="failed" link @click="list.load">
              加载失败，请重试
            </el-button><span v-else>暂无任务</span>
          </template>
          <el-table-column label="名称" min-width="180">
            <template #default="{ row }">
              <el-button link type="primary" @click="router.push(`/app/jobs/${row.id}`)">
                {{ row.name || row.id }}
              </el-button>
            </template>
          </el-table-column>
          <el-table-column prop="workspace_id" label="工作区" min-width="110">
            <template #default="{ row }">
              {{ row.workspace_id || '未绑定' }}
            </template>
          </el-table-column>
          <el-table-column label="执行计划" min-width="150">
            <template #default="{ row }">
              {{ scheduleLabel(row.schedule) }}
            </template>
          </el-table-column>
          <el-table-column label="启用状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.scheduler.enabled ? 'success' : 'info'">
                {{ row.schedule.kind === 'manual' ? '不适用' : row.scheduler.enabled ? '已启用' : '已暂停' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="最近运行" min-width="110">
            <template #default="{ row }">
              {{ row.latest_run ? runLabels[row.latest_run.status as Run['status']] : '尚未运行' }}
            </template>
          </el-table-column>
          <el-table-column label="操作" fixed="right" width="160">
            <template #default="{ row }">
              <div class="admin-actions-cell">
                <el-button link type="primary" size="small" @click="router.push(`/app/jobs/${row.id}`)">
                  详情
                </el-button>
                <el-button link type="success" size="small" :disabled="actions.busy.value" @click="edit(row)">
                  编辑
                </el-button>
                <el-dropdown :disabled="actions.busy.value" @command="command => actions.execute(row, command)">
                  <el-button link type="info" size="small">
                    更多
                  </el-button><template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="run">
                        立即执行
                      </el-dropdown-item>
                      <el-dropdown-item :command="row.scheduler.enabled ? 'pause' : 'resume'" :disabled="row.schedule.kind === 'manual'">
                        {{ row.scheduler.enabled ? '暂停' : '恢复' }}
                      </el-dropdown-item>
                      <el-dropdown-item command="delete" divided>
                        删除
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div class="admin-pager">
        <el-pagination :total="pager.total" :page-size="pager.pageSize" :current-page="pager.currentPage" :page-sizes="pager.pageSizes" :layout="pager.layout" @current-change="list.changePage" @size-change="list.changeSize" />
      </div>
    </el-card>
    <JobEditor v-if="editor" :job="editing" :timezone="timezone" @close="editor = false" @saved="saved" />
  </div>
</template>
