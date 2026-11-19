<script setup lang="ts">
import type { LoadFunction } from "element-plus"
import type { ScriptEntry } from "./api"
import CodeViewer from "@@/components/CodeViewer/index.vue"
import { useDevice } from "@@/composables/useDevice"
import { Document, Folder, Refresh } from "@element-plus/icons-vue"
import { getScriptDirectory, getScriptFile, getScriptProjects } from "./api"

defineOptions({ name: "Scripts" })
interface TreeEntry extends ScriptEntry { project: string, key: string, leaf: boolean }
interface OpenFile { key: string, project: string, path: string, content: string, loading: boolean, failed: boolean }
const { isMobile } = useDevice()
const treeWidth = ref<number | string>(280)
const explorerSize = computed({
  get: () => isMobile.value ? 180 : treeWidth.value,
  set: (value) => {
    if (!isMobile.value) treeWidth.value = value
  }
})
const route = useRoute()
const router = useRouter()
const projects = ref<string[]>([])
const search = ref("")
const files = ref<OpenFile[]>([])
const active = ref("")
const treeVersion = ref(0)
const expanded = ref<string[]>([])
const busy = ref(false)
const treeFailed = ref(false)
const projectsFailed = ref(false)
const requests = new Map<string, number>()
let disposed = false
function key(project: string, path: string): string {
  return JSON.stringify([project, path])
}
const roots = computed<TreeEntry[]>(() => projects.value
  .filter(project => project.toLocaleLowerCase().includes(search.value.trim().toLocaleLowerCase()))
  .map(project => ({ name: project, path: "", kind: "directory", project, key: key(project, ""), leaf: false })))
const missingProject = computed(() => route.name === "Scripts" && typeof route.query.project === "string" && !projectsFailed.value && !busy.value && !projects.value.includes(route.query.project))

function reveal(project: string, path = ""): void {
  if (!project.toLocaleLowerCase().includes(search.value.trim().toLocaleLowerCase())) search.value = ""
  const parts = path.split("/")
  for (let index = 0; index < parts.length; index++) {
    const parent = key(project, parts.slice(0, index).join("/"))
    if (!expanded.value.includes(parent)) expanded.value.push(parent)
  }
}
watch(() => [route.name, route.query.project, route.query.file], () => {
  if (route.name !== "Scripts" || typeof route.query.project !== "string") return
  const project = route.query.project
  const path = typeof route.query.file === "string" ? route.query.file : ""
  reveal(project, path)
  if (path) void open(project, path, false)
  else active.value = files.value.find(file => file.project === project)?.key || ""
}, { immediate: true })
onMounted(refresh)
onBeforeUnmount(() => {
  disposed = true
})

async function read(file: OpenFile): Promise<void> {
  const revision = (requests.get(file.key) || 0) + 1
  requests.set(file.key, revision)
  try {
    const result = await getScriptFile(file.project, file.path)
    if (disposed || requests.get(file.key) !== revision) return
    file.content = result.content
    file.failed = false
  } catch {
    if (!disposed && requests.get(file.key) === revision) file.failed = true
  } finally {
    if (!disposed && requests.get(file.key) === revision) file.loading = false
  }
}
function navigate(file?: OpenFile): void {
  void router.replace({ query: file ? { project: file.project, file: file.path } : {} })
}
async function open(project: string, path: string, updateRoute = true): Promise<void> {
  active.value = key(project, path)
  const existing = files.value.find(file => file.key === active.value)
  if (existing) {
    if (updateRoute) navigate(existing)
    return
  }
  const file = reactive<OpenFile>({ key: active.value, project, path, content: "", loading: true, failed: false })
  files.value.push(file)
  if (updateRoute) navigate(file)
  await read(file)
}
const load: LoadFunction = async (node, resolve, reject) => {
  if (node.level === 0) return resolve(roots.value)
  const revision = treeVersion.value
  const entry = node.data as TreeEntry
  try {
    const result = await getScriptDirectory(entry.project, entry.path)
    if (disposed || revision !== treeVersion.value) return resolve([])
    treeFailed.value = false
    resolve(result.entries.map(item => ({ ...item, project: entry.project, key: key(entry.project, item.path), leaf: item.kind === "file" })))
  } catch {
    if (!disposed && revision === treeVersion.value) treeFailed.value = true
    reject?.()
  }
}
function click(entry: TreeEntry): void {
  if (entry.kind === "file") void open(entry.project, entry.path)
}
function close(identity: string): void {
  const index = files.value.findIndex(file => file.key === identity)
  if (index < 0) return
  files.value.splice(index, 1)
  requests.set(identity, (requests.get(identity) || 0) + 1)
  if (active.value === identity) {
    const next = files.value[Math.min(index, files.value.length - 1)]
    active.value = next?.key || ""
    navigate(next)
  }
}
function label(file: OpenFile): string {
  const name = file.path.split("/").pop() || file.path
  return files.value.some(other => other.key !== file.key && other.path.split("/").pop() === name) ? `${file.project}/${file.path}` : name
}
async function refresh(): Promise<void> {
  busy.value = true
  treeFailed.value = false
  try {
    const result = await getScriptProjects()
    if (disposed) return
    projects.value = result.projects
    projectsFailed.value = false
    treeVersion.value++
  } catch {
    if (!disposed) projectsFailed.value = true
  } finally {
    await Promise.all(files.value.map(file => read(file)))
    if (!disposed) busy.value = false
  }
}
</script>

<template>
  <div class="script-project">
    <el-splitter :layout="isMobile ? 'vertical' : 'horizontal'">
      <el-splitter-panel v-model:size="explorerSize" :min="isMobile ? 100 : 160" :max="isMobile ? 220 : '45%'" :resizable="!isMobile">
        <aside class="script-files" aria-label="脚本文件树">
          <div class="tree-header">
            <el-input v-model="search" clearable placeholder="搜索脚本项目" aria-label="搜索脚本项目" />
            <el-button text :icon="Refresh" :disabled="busy" aria-label="刷新脚本" title="刷新目录和打开的文件" @click="refresh" />
          </div>
          <p v-if="projectsFailed || treeFailed" class="file-notice" role="alert">
            目录读取失败，请刷新重试。
          </p>
          <p v-if="missingProject" class="file-notice" role="alert">
            关联的脚本项目不存在，请核对任务配置或刷新目录。
          </p>
          <el-tree v-if="!projectsFailed" :key="treeVersion" :data="roots" :load="load" lazy node-key="key" :props="{ label: 'name', isLeaf: 'leaf' }" :current-node-key="active" :default-expanded-keys="expanded" highlight-current empty-text="暂无匹配的脚本项目" @node-click="click" @node-expand="(entry: TreeEntry) => { if (!expanded.includes(entry.key)) expanded.push(entry.key) }" @node-collapse="(entry: TreeEntry) => { expanded = expanded.filter(identity => identity !== entry.key) }">
            <template #default="{ data }">
              <span class="tree-file" :title="`${data.project}/${data.path}`">
                <el-icon><Folder v-if="data.kind === 'directory'" /><Document v-else /></el-icon>
                <span>{{ data.name }}</span>
              </span>
            </template>
          </el-tree>
        </aside>
      </el-splitter-panel>
      <el-splitter-panel :min="isMobile ? 160 : 280">
        <section class="script-code" aria-label="脚本源码">
          <el-tabs v-if="files.length" v-model="active" type="card" closable class="file-tabs" @tab-remove="identity => close(String(identity))" @tab-change="identity => navigate(files.find(file => file.key === identity))">
            <el-tab-pane v-for="file in files" :key="file.key" :name="file.key" :label="label(file)">
              <template #label>
                <span :title="`${file.project}/${file.path}`">{{ label(file) }}</span>
              </template>
            </el-tab-pane>
          </el-tabs>
          <div v-for="file in files" v-show="active === file.key" :key="file.key" class="file-content">
            <p v-if="file.loading" class="file-notice">
              正在读取文件…
            </p>
            <p v-else-if="file.failed" class="file-notice" role="alert">
              文件无法预览，请核对文件是否存在、为 UTF-8 文本且未超过大小限制，然后从左侧刷新。
            </p>
            <CodeViewer v-else :path="file.path" :content="file.content" :active="active === file.key" />
          </div>
          <p v-if="!active" class="file-notice">
            从左侧选择文件查看源码
          </p>
        </section>
      </el-splitter-panel>
    </el-splitter>
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
  height: 100%;
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
  height: 100%;
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
    border-right: 0;
    border-bottom: 1px solid var(--el-border-color);
  }
}
</style>
