<script setup lang="ts">
import type { LoadFunction } from "element-plus"
import type { ScriptEntry } from "./api"
import CodeViewer from "@@/components/CodeViewer/index.vue"
import { Document, Folder, Refresh } from "@element-plus/icons-vue"
import { useTagsViewStore } from "@/pinia/stores/tags-view"
import { getScriptDirectory, getScriptFile } from "./api"

defineOptions({ name: "ScriptProject" })
interface OpenFile { path: string, content: string, loading: boolean, failed: boolean }
const route = useRoute()
const router = useRouter()
const project = String(route.params.project)
const initialPath = typeof route.query.file === "string" ? route.query.file : ""
const tags = useTagsViewStore()
const files = ref<OpenFile[]>([])
const active = ref("")
const treeVersion = ref(0)
const expanded = ref<string[]>([])
const busy = ref(false)
const treeFailed = ref(false)
let disposed = false
const requests = new Map<string, number>()
onMounted(() => {
  tags.setVisitedTitle(route.path, `脚本 · ${project}`)
  if (initialPath) void open(initialPath)
})
onBeforeUnmount(() => {
  disposed = true
})

async function read(file: OpenFile): Promise<void> {
  const revision = (requests.get(file.path) || 0) + 1
  requests.set(file.path, revision)
  try {
    const result = await getScriptFile(project, file.path)
    if (disposed || requests.get(file.path) !== revision) return
    file.content = result.content
    file.failed = false
  } catch {
    if (!disposed && requests.get(file.path) === revision) file.failed = true
  } finally {
    if (!disposed && requests.get(file.path) === revision) file.loading = false
  }
}
async function open(path: string): Promise<void> {
  active.value = path
  void router.replace({ query: { file: path } })
  if (files.value.some(file => file.path === path)) return
  files.value.push({ path, content: "", loading: true, failed: false })
  await read(files.value[files.value.length - 1])
}
const load: LoadFunction = async (node, resolve, reject) => {
  const revision = treeVersion.value
  try {
    const path = node.level === 0 ? "" : String(node.data.path)
    const result = await getScriptDirectory(project, path)
    if (disposed || revision !== treeVersion.value) return resolve([])
    treeFailed.value = false
    resolve(result.entries.map(entry => ({ ...entry, leaf: entry.kind === "file" })))
  } catch {
    if (!disposed && revision === treeVersion.value) treeFailed.value = true
    reject?.()
  }
}
function click(entry: ScriptEntry): void {
  if (entry.kind === "file") void open(entry.path)
}
function close(path: string): void {
  const index = files.value.findIndex(file => file.path === path)
  if (index < 0) return
  files.value.splice(index, 1)
  requests.set(path, (requests.get(path) || 0) + 1)
  if (active.value === path) {
    active.value = files.value[Math.min(index, files.value.length - 1)]?.path || ""
    void router.replace({ query: active.value ? { file: active.value } : {} })
  }
}
async function refresh(): Promise<void> {
  busy.value = true
  treeFailed.value = false
  treeVersion.value++
  try {
    await Promise.all(files.value.map(file => read(file)))
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="script-project">
    <aside class="script-files" aria-label="脚本文件树">
      <div class="tree-header">
        <span :title="project">{{ project }}</span>
        <el-button text :icon="Refresh" :disabled="busy" aria-label="刷新脚本" title="刷新目录和打开的文件" @click="refresh" />
      </div>
      <p v-if="treeFailed" class="file-notice" role="alert">
        目录读取失败，请刷新重试。
      </p>
      <el-tree :key="treeVersion" :load="load" lazy node-key="path" :props="{ label: 'name', isLeaf: 'leaf' }" :current-node-key="active" :default-expanded-keys="expanded" highlight-current empty-text="暂无文件" @node-click="click" @node-expand="(entry: ScriptEntry) => { if (!expanded.includes(entry.path)) expanded.push(entry.path) }" @node-collapse="(entry: ScriptEntry) => { expanded = expanded.filter(path => path !== entry.path) }">
        <template #default="{ data }">
          <span class="tree-file" :title="data.path">
            <el-icon><Folder v-if="data.kind === 'directory'" /><Document v-else /></el-icon>
            <span>{{ data.name }}</span>
          </span>
        </template>
      </el-tree>
    </aside>
    <section class="script-code" aria-label="脚本源码">
      <el-tabs v-if="files.length" v-model="active" type="card" closable class="file-tabs" @tab-remove="path => close(String(path))" @tab-change="path => router.replace({ query: { file: String(path) } })">
        <el-tab-pane v-for="file in files" :key="file.path" :name="file.path" :label="file.path.split('/').pop()">
          <template #label>
            <span :title="file.path">{{ file.path.split('/').pop() }}</span>
          </template>
        </el-tab-pane>
      </el-tabs>
      <div v-for="file in files" v-show="active === file.path" :key="file.path" class="file-content">
        <p v-if="file.loading" class="file-notice">
          正在读取文件…
        </p>
        <p v-else-if="file.failed" class="file-notice" role="alert">
          文件无法预览，请核对文件是否存在、为 UTF-8 文本且未超过大小限制，然后从左侧刷新。
        </p>
        <CodeViewer v-else :path="file.path" :content="file.content" :active="active === file.path" />
      </div>
      <p v-if="!files.length" class="file-notice">
        从左侧选择文件查看源码
      </p>
    </section>
  </div>
</template>

<style scoped lang="scss">
.script-project {
  display: flex;
  min-width: 0;
  height: calc(100dvh - var(--v3-header-height));
  min-height: 380px;
  margin: 0;
  border: 1px solid var(--el-border-color);
  background: var(--el-bg-color);
  overflow: hidden;
}
.script-files {
  flex: 0 0 240px;
  min-width: 0;
  overflow: auto;
  border-right: 1px solid var(--el-border-color);
  background: var(--el-fill-color-light);
  :deep(.el-tree) {
    background: transparent;
  }
}
.tree-header {
  position: sticky;
  top: 0;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  height: 44px;
  padding: 0 12px;
  background: var(--el-fill-color-light);
  > span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}
.tree-file {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  font-size: 13px;
  > span {
    overflow: hidden;
    text-overflow: ellipsis;
  }
}
.script-code {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
.file-tabs {
  flex: 0 0 auto;
  :deep(.el-tabs__header .el-tabs__nav),
  :deep(.el-tabs__item) {
    border-radius: 0;
  }
  :deep(.el-tabs__header .el-tabs__item .is-icon-close) {
    width: 14px;
  }
  :deep(.el-tabs__header .el-tabs__nav .el-tabs__item.is-closable) {
    padding: 0 20px;
  }
  :deep(.el-tabs__header) {
    margin: 0;
  }
  :deep(.el-tabs__content) {
    display: none;
  }
}

.file-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.file-notice {
  padding: 16px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
@media (max-width: 768px) {
  .script-project {
    flex-direction: column;
  }
  .script-files {
    flex-basis: 180px;
    border-right: 0;
    border-bottom: 1px solid var(--el-border-color);
  }
}
</style>
