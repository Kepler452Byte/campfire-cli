<script setup lang="ts">
import type { LogChunk, Run } from "../types"
import { ElMessage } from "element-plus"
import { getLogs, getRun } from "../api"

const props = defineProps<{ runId: string }>()
const emit = defineEmits<{ loaded: [run: Run] }>()
const run = ref<Run>()
const chunks = ref<LogChunk[]>([])
const stream = ref("stdout")
const tabs = ["stdout", "stderr"]
const failed = ref(false)
const truncated = ref(false)
const content = computed(() => chunks.value.filter(chunk => chunk.stream === stream.value).map(chunk => chunk.content).join(""))
let timer: ReturnType<typeof setTimeout> | undefined
let generation = 0
let cursor = 0
async function load(seq = generation): Promise<void> {
  clearTimeout(timer)
  failed.value = false
  try {
    const result = await getRun(props.runId)
    const logs = await getLogs(props.runId, cursor)
    if (seq !== generation) return
    run.value = result.run
    emit("loaded", result.run)
    chunks.value.push(...logs.chunks)
    cursor = logs.next_cursor
    truncated.value = logs.truncated
    if (run.value.status === "running" || logs.chunks.length === 100) timer = setTimeout(() => void load(seq), logs.chunks.length === 100 ? 50 : 2000)
  } catch {
    if (seq === generation) failed.value = true
  }
}
watch(() => props.runId, () => {
  generation++
  cursor = 0
  chunks.value = []
  run.value = undefined
  truncated.value = false
  void load()
}, { immediate: true })
onScopeDispose(() => {
  generation++
  clearTimeout(timer)
})
async function copy(): Promise<void> {
  try {
    await navigator.clipboard.writeText(content.value)
    ElMessage.success("已复制")
  } catch {
    ElMessage.error("复制失败，请手动选择日志")
  }
}
</script>

<template>
  <section class="run-logs">
    <el-alert v-if="failed" title="日志刷新失败，以下为已读取内容" type="error" :closable="false">
      <el-button link @click="load()">
        重试
      </el-button>
    </el-alert>
    <el-alert v-if="truncated" title="日志达到记录上限，部分输出已截断" type="warning" :closable="false" />
    <el-tabs v-model="stream" class="log-tabs">
      <el-tab-pane v-for="item in tabs" :key="item" :name="item" :label="item">
        <div v-if="stream === item" class="log-content">
          <el-button class="log-copy" size="small" text @click="copy">
            复制
          </el-button>
          <pre tabindex="0" aria-label="运行日志">{{ content || '暂无输出' }}</pre>
        </div>
      </el-tab-pane>
    </el-tabs>
  </section>
</template>

<style scoped lang="scss">
.run-logs {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
.log-content {
  position: relative;
  display: flex;
  flex: 1;
  min-height: 200px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  overflow: hidden;
}
.log-copy {
  position: absolute;
  top: 12px;
  right: 12px;
}
.log-tabs {
  flex: 1;
  min-width: 0;
  min-height: 0;
  :deep(.el-tabs__content),
  :deep(.el-tab-pane) {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
  }
}
pre {
  flex: 1;
  min-width: 0;
  margin: 0;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  padding: 48px 16px 16px;
}
</style>
