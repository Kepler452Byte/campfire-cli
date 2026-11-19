<script setup lang="ts">
import type { Run } from "../types"
import { useList } from "@@/composables/use-list"
import { listAllRuns, listRuns } from "../api"
import { runLabels, startedLabel } from "../types"

const props = defineProps<{ jobId?: string }>()
const router = useRouter()
const search = ref("")
const filter = ref("")
const history = useList<Run>((page, size) => props.jobId ? listRuns(props.jobId, page, size) : listAllRuns(page, size, filter.value))
const { rows, pager, loading, failed } = history
function query(): void {
  filter.value = search.value.trim()
  void history.search()
}
const refreshTimer = setInterval(() => {
  if (!document.hidden && !loading.value && !failed.value) void history.load()
}, 5000)
onScopeDispose(() => clearInterval(refreshTimer))
</script>

<template>
  <div :class="jobId ? 'run-history' : 'admin-page'">
    <el-card v-if="!jobId" class="admin-search" shadow="never">
      <el-form inline class="admin-search__form" @submit.prevent="query">
        <el-form-item label="任务 ID">
          <el-input v-model="search" clearable aria-label="筛选运行记录的任务 ID" @clear="query" />
        </el-form-item>
        <el-form-item class="admin-search__actions">
          <el-button native-type="submit">
            查询
          </el-button>
          <el-button @click="search = ''; query()">
            重置
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
    <el-card class="admin-table" shadow="never">
      <div :class="{ 'admin-table__body': !jobId }">
        <el-table :data="rows" row-key="id" :height="jobId ? undefined : '100%'">
          <template #empty>
            <el-button v-if="failed" link @click="history.load">
              加载失败，请重试
            </el-button>
            <span v-else>暂无运行记录</span>
          </template>
          <el-table-column v-if="!jobId" prop="job_id" label="任务 ID" min-width="180" />
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
          <el-table-column label="退出码" width="90">
            <template #default="{ row }">
              {{ row.exit_code ?? '—' }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="router.push(`/app/jobs/${row.job_id}/runs/${row.id}`)">
                查看日志
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div class="admin-pager">
        <el-pagination :total="pager.total" :page-size="pager.pageSize" :current-page="pager.currentPage" :page-sizes="pager.pageSizes" :layout="jobId ? 'total, prev, pager, next' : pager.layout" @current-change="history.changePage" @size-change="history.changeSize" />
      </div>
    </el-card>
  </div>
</template>

<style scoped lang="scss">
.run-history > .el-card {
  border: 0;
  background: transparent;
  :deep(.el-card__body) {
    padding: 0;
  }
}
</style>
