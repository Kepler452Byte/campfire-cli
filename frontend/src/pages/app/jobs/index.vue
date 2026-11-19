<script setup lang="ts">
import JobList from "./components/JobList.vue"
import RunHistory from "./components/RunHistory.vue"

const route = useRoute()
const router = useRouter()
const tab = computed({
  get: () => route.query.tab === "runs" ? "runs" : "jobs",
  set: (value) => {
    void router.replace({ query: value === "runs" ? { tab: "runs" } : {} })
  }
})
</script>

<template>
  <div class="job-center">
    <el-tabs v-model="tab">
      <el-tab-pane label="任务" name="jobs" />
      <el-tab-pane label="运行记录" name="runs" />
    </el-tabs>
    <JobList v-if="tab === 'jobs'" />
    <RunHistory v-else />
  </div>
</template>

<style scoped lang="scss">
.job-center {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  > .el-tabs {
    padding: 12px 20px 0;
    :deep(.el-tabs__header) {
      margin: 0;
    }
  }
  > .admin-page {
    flex: 1;
    min-height: 0;
  }
}
</style>
