<script setup lang="ts">
import type { Run } from "./types"
import { useTagsViewStore } from "@/pinia/stores/tags-view"
import { getJob } from "./api"
import RunLogs from "./components/RunLogs.vue"
import { runLabels, startedLabel } from "./types"

const route = useRoute()
const jobId = String(route.params.id)
const runId = String(route.params.runId)
const pagePath = route.path
const jobName = ref(jobId)
const run = ref<Run>()
const tags = useTagsViewStore()

watch([jobName, run], () => {
  const time = run.value ? startedLabel(run.value).slice(5) : ""
  tags.setVisitedTitle(pagePath, `日志 · ${jobName.value}${time ? ` · ${time}` : ""}`)
})
onMounted(async () => {
  try {
    const result = await getJob(jobId)
    jobName.value = result.job.name || jobId
  } catch {
    // 已删除任务的运行日志仍可按原任务 id 查看。
  }
})
</script>

<template>
  <div class="run-page">
    <div class="three-line-table-wrap">
      <table class="three-line-table" aria-label="本次运行">
        <thead>
          <tr>
            <th scope="col">
              任务
            </th>
            <th scope="col">
              开始时间
            </th>
            <th scope="col">
              耗时
            </th>
            <th scope="col">
              状态
            </th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>{{ jobName }}</td>
            <td>{{ run ? startedLabel(run) : '—' }}</td>
            <td>{{ !run || run.duration == null ? '—' : `${run.duration.toFixed(1)} 秒` }}</td>
            <td>
              <el-tag v-if="run">
                {{ runLabels[run.status] }}
              </el-tag><span v-else>—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <RunLogs :run-id="runId" @loaded="run = $event" />
  </div>
</template>

<style scoped lang="scss">
.run-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
  padding: 20px;
}
</style>
