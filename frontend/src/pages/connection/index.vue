<script setup lang="ts">
import type { ConnectionState } from "@/http/session"
import logoUrl from "@@/assets/images/layouts/logo.svg?url"
import { connect, ticketFromLink } from "@/http/session"

const props = defineProps<{ state: ConnectionState }>()
const link = ref("")
const inputError = ref("")
const titles: Record<ConnectionState, string> = {
  "connecting": "正在连接",
  "ready": "连接已建立",
  "session-required": "需要重新连接",
  "invalid-ticket": "连接链接已失效",
  "unreachable": "暂时无法连接服务",
  "initialization-error": "页面初始化失败"
}
const descriptions: Record<ConnectionState, string> = {
  "connecting": "正在确认本机 Web 会话。",
  "ready": "",
  "session-required": "当前浏览器尚未连接，或 Web 重启后原会话已失效。",
  "invalid-ticket": "链接可能已经使用，或来自上一次运行的 Web。",
  "unreachable": "请确认 Web 仍在运行，并检查当前访问地址或端口转发。",
  "initialization-error": "服务响应或页面加载异常，请重新加载；仍失败时检查运行环境。"
}
const target = location.pathname + location.search
async function submit(): Promise<void> {
  inputError.value = ""
  try {
    const ticket = ticketFromLink(link.value)
    await connect(ticket)
  } catch {
    inputError.value = "请输入 CLI 输出的完整连接链接"
  }
}
function retry(): void {
  if (props.state === "initialization-error") location.reload()
  else void connect()
}
</script>

<template>
  <main class="connection-page">
    <section class="connection-card" aria-label="Campfire 连接">
      <header><img :src="logoUrl" alt=""><span>Campfire</span></header>
      <h1>{{ titles[state] }}</h1>
      <p role="status">
        {{ descriptions[state] }}
      </p>
      <template v-if="state !== 'connecting'">
        <p>当前页面 <code>{{ target }}</code></p>
        <template v-if="state !== 'initialization-error'">
          <p>在当前设备终端执行以下命令，获取新的连接链接；已有服务会继续运行。</p>
          <pre>campfire web --no-open</pre>
          <el-form @submit.prevent="submit">
            <el-form-item label="新的连接链接" :error="inputError">
              <el-input v-model="link" type="password" show-password clearable autocomplete="off" aria-label="新的连接链接" placeholder="粘贴 CLI 输出的连接链接" />
            </el-form-item>
            <div class="connection-actions">
              <el-button type="primary" native-type="submit" :disabled="!link.trim()">
                连接
              </el-button>
              <el-button @click="retry">
                重试连接
              </el-button>
            </div>
          </el-form>
          <p class="connection-note">
            连接成功后回到当前页面。刚才操作若未确认完成，请重新连接后核对结果。
          </p>
        </template>
        <el-button v-else @click="retry">
          重新加载
        </el-button>
      </template>
    </section>
  </main>
</template>

<style scoped lang="scss">
.connection-page {
  min-height: 100dvh;
  font-family: var(--el-font-family);
  display: grid;
  place-items: center;
  padding: 24px;
  box-sizing: border-box;
  background: var(--el-bg-color-page);
  color: var(--el-text-color-primary);
}
.connection-card {
  width: 100%;
  max-width: 520px;
  padding: 28px;
  box-sizing: border-box;
  border: 1px solid var(--el-border-color-light);
  background: var(--el-bg-color);
  border-radius: 8px;
  header {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 24px;
    font-weight: 600;
  }
  img {
    width: 38px;
    height: 38px;
  }
  h1 {
    margin: 28px 0 12px;
    font-size: 22px;
  }
  p {
    line-height: 1.7;
    overflow-wrap: anywhere;
  }
  pre {
    padding: 12px;
    background: var(--el-fill-color-light);
    overflow: auto;
  }
  .el-form {
    margin-top: 24px;
  }
  .el-form-item {
    display: block;
  }
}
.connection-actions {
  display: flex;
  gap: 10px;
  .el-button {
    margin-left: 0;
  }
}
.connection-note {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-bottom: 0;
}
@media (max-width: 480px) {
  .connection-page {
    padding: 16px;
  }
  .connection-card {
    padding: 20px;
  }
}
</style>
