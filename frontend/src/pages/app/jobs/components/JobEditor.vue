<script setup lang="ts">
import type { Job, Plan, Schedule } from "../types"
import { ElMessage } from "element-plus"
import { getScriptProjects } from "../../scripts/api"
import { getWorkspaces, saveJob } from "../api"
import { scheduleLabel } from "../types"

const props = defineProps<{ job?: Job, timezone: string }>()
const emit = defineEmits<{ saved: [], close: [] }>()
const model = ref<Job>(props.job
  ? structuredClone(toRaw(props.job))
  : {
      id: "",
      name: "",
      argv: [],
      cwd: "",
      timeout: 360,
      workspace_id: null,
      schedule: { kind: "manual" }
    })
const workspace = ref(model.value.workspace_id ?? "")
const scriptProject = ref(model.value.script_project ?? "")
const kind = ref<"command" | "codex" | "claude">(model.value.agent?.kind ?? "command")
const executable = ref(model.value.agent?.executable ?? model.value.argv?.[0] ?? "")
const args = ref(JSON.stringify(model.value.agent?.args ?? model.value.argv?.slice(1) ?? []))
const prompt = ref(model.value.agent?.prompt ?? "")
const minutes = ref((model.value.schedule.seconds ?? 60) / 60)
const time = ref(model.value.schedule.time ?? "22:30")
const day = ref(model.value.schedule.day ?? "mon")
const workspaceOptions = ref<string[]>([])
const scriptProjects = ref<string[]>([])
const saving = ref(false)
const plan = ref<Plan>()
const submission = ref<Job>()
const advanced = ref<string[]>(["execution"])

onMounted(async () => {
  try {
    workspaceOptions.value = Object.keys((await getWorkspaces()).workspaces)
  } catch {
    // 请求层报告加载失败；保留表单中已有的绑定。
  }
})
onMounted(async () => {
  try {
    scriptProjects.value = (await getScriptProjects()).projects
  } catch {
    // 查询失败时保留已有选择，执行配置仍可核对。
  }
})
function build(): Job {
  const parameters: unknown = JSON.parse(args.value)
  if (!Array.isArray(parameters) || !parameters.every(arg => typeof arg === "string")) throw new Error("参数需为 JSON 字符串数组")
  const schedule: Schedule = { kind: model.value.schedule.kind }
  if (schedule.kind === "interval") schedule.seconds = minutes.value * 60
  if (schedule.kind === "daily" || schedule.kind === "weekly") schedule.time = time.value
  if (schedule.kind === "weekly") schedule.day = day.value
  const job: Job = { id: model.value.id, name: model.value.name || null, cwd: model.value.cwd, workspace_id: workspace.value || null, timeout: model.value.timeout, schedule }
  if (scriptProject.value) job.script_project = scriptProject.value
  if (kind.value === "command") job.argv = [executable.value, ...parameters]
  else job.agent = { kind: kind.value, executable: executable.value, args: parameters, prompt: prompt.value }
  return job
}
async function preview(): Promise<void> {
  saving.value = true
  try {
    submission.value = build()
    plan.value = await saveJob(submission.value, !!props.job)
  } catch (error) {
    if (error instanceof SyntaxError || (error instanceof Error && error.message === "参数需为 JSON 字符串数组")) ElMessage.error(error.message)
  } finally {
    saving.value = false
  }
}
async function confirm(): Promise<void> {
  if (!submission.value || !plan.value) return
  saving.value = true
  try {
    await saveJob(submission.value, !!props.job, plan.value.expected_plan)
    ElMessage.success("配置已保存")
    emit("saved")
  } catch {
    plan.value = undefined
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-dialog :model-value="true" :title="job ? '编辑任务' : '新增任务'" width="720px" class="admin-dialog--primary" align-center :close-on-click-modal="false" :close-on-press-escape="!saving" :show-close="!saving" @close="emit('close')">
    <el-form v-if="!plan" label-width="88px" :disabled="saving" @submit.prevent="preview">
      <el-form-item label="名称">
        <el-input v-model="model.name" aria-label="名称" />
      </el-form-item>
      <el-form-item label="任务 ID" required>
        <el-input v-model="model.id" :disabled="!!job" placeholder="例如 daily-growth，创建后保持稳定" aria-label="任务 ID" />
      </el-form-item>
      <el-form-item label="工作区">
        <el-select v-model="workspace" clearable placeholder="未绑定" aria-label="工作区">
          <el-option v-for="id in workspaceOptions" :key="id" :label="id" :value="id" />
        </el-select>
      </el-form-item>
      <el-form-item label="脚本项目">
        <el-select v-model="scriptProject" clearable placeholder="未关联" aria-label="脚本项目">
          <el-option v-for="project in scriptProjects" :key="project" :label="project" :value="project" />
        </el-select>
      </el-form-item>
      <el-form-item label="执行方式">
        <el-select v-model="kind" aria-label="执行方式">
          <el-option label="普通命令" value="command" /><el-option label="Codex" value="codex" /><el-option label="Claude Code" value="claude" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="kind !== 'command'" label="提示词" required>
        <el-input v-model="prompt" type="textarea" :rows="8" aria-label="提示词" />
      </el-form-item>
      <el-form-item label="执行计划">
        <el-select v-model="model.schedule.kind" aria-label="执行计划">
          <el-option label="仅手动" value="manual" /><el-option label="固定间隔" value="interval" /><el-option label="每天" value="daily" /><el-option label="每周" value="weekly" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="model.schedule.kind === 'interval'" label="间隔分钟">
        <el-input v-model.number="minutes" inputmode="numeric" aria-label="间隔分钟" />
      </el-form-item>
      <el-form-item v-if="model.schedule.kind === 'weekly'" label="星期">
        <el-select v-model="day">
          <el-option v-for="(label, key) in { mon: '一', tue: '二', wed: '三', thu: '四', fri: '五', sat: '六', sun: '日' }" :key="key" :label="`周${label}`" :value="key" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="['daily', 'weekly'].includes(model.schedule.kind)" label="时间">
        <el-time-select v-model="time" start="00:00" end="23:59" step="00:01" />
      </el-form-item>
      <el-form-item label="执行时区">
        {{ timezone }}
      </el-form-item>
      <el-form-item label="超时秒数">
        <el-input v-model.number="model.timeout" inputmode="numeric" aria-label="超时秒数" />
      </el-form-item>
      <el-collapse v-model="advanced">
        <el-collapse-item title="执行程序、参数与工作目录" name="execution">
          <el-form-item label="程序路径" required>
            <el-input v-model="executable" placeholder="当前设备的绝对路径" aria-label="程序路径" />
          </el-form-item>
          <el-form-item label="额外参数">
            <el-input v-model="args" type="textarea" :rows="3" placeholder="JSON 字符串数组，例如 []" aria-label="额外参数" />
          </el-form-item>
          <el-form-item label="工作目录" required>
            <el-input v-model="model.cwd" placeholder="当前设备的绝对路径" aria-label="工作目录" />
          </el-form-item>
        </el-collapse-item>
      </el-collapse>
      <el-text v-if="!job && model.schedule.kind !== 'manual'" type="info">
        新任务创建后处于暂停状态，可在列表中启用。
      </el-text>
    </el-form>
    <template v-else-if="submission">
      <el-alert title="核对本次配置后确认保存" type="info" :closable="false" />
      <el-descriptions :column="1" border class="preview">
        <el-descriptions-item label="名称">
          {{ submission.name || submission.id }}
        </el-descriptions-item>
        <el-descriptions-item label="工作区">
          {{ submission.workspace_id || '未绑定' }}
        </el-descriptions-item>
        <el-descriptions-item label="执行计划">
          {{ scheduleLabel(submission.schedule) }} · {{ timezone }}
        </el-descriptions-item>
        <el-descriptions-item label="保存后状态">
          {{ submission.schedule.kind === 'manual' ? '仅手动执行' : plan.enabled_after ? '已启用，将按此计划运行' : '已暂停，不会定时运行' }}
        </el-descriptions-item>
        <el-descriptions-item v-if="submission.script_project" label="脚本项目">
          {{ submission.script_project }}
        </el-descriptions-item>
        <el-descriptions-item label="程序">
          {{ executable }}
        </el-descriptions-item>
        <el-descriptions-item label="工作目录">
          {{ submission.cwd }}
        </el-descriptions-item>
        <el-descriptions-item label="超时">
          {{ submission.timeout }} 秒
        </el-descriptions-item>
        <el-descriptions-item label="参数">
          <pre>{{ args }}</pre>
        </el-descriptions-item>
        <el-descriptions-item v-if="submission.agent" label="提示词">
          <pre>{{ submission.agent.prompt }}</pre>
        </el-descriptions-item>
      </el-descriptions>
    </template>
    <template #footer>
      <el-button :disabled="saving" @click="plan ? (plan = undefined) : emit('close')">
        {{ plan ? '返回修改' : '取消' }}
      </el-button>
      <el-button type="primary" :loading="saving" @click="plan ? confirm() : preview()">
        {{ plan ? '确认保存' : '预览变更' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped lang="scss">
.preview {
  margin-top: 16px;
  overflow-wrap: anywhere;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  margin: 0;
}
</style>
