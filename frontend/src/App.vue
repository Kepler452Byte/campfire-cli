<script lang="ts" setup>
import { useTheme } from "@@/composables/useTheme"
import zhCn from "element-plus/es/locale/lang/zh-cn" // Element Plus 中文包
import { connect, connection } from "@/http/session"
import ConnectionPage from "@/pages/connection/index.vue"

const props = defineProps<{ ticket?: string }>()
const { initTheme } = useTheme()
const router = useRouter()
const routeReady = ref(false)
const pageFailed = ref(false)
const state = computed(() => pageFailed.value ? "initialization-error" : connection.value === "ready" && !routeReady.value ? "connecting" : connection.value)
initTheme()
function failPage(): false {
  pageFailed.value = true
  return false
}
onErrorCaptured(failPage)
const removeErrorHandler = router.onError(() => {
  pageFailed.value = true
})
onScopeDispose(removeErrorHandler)
onMounted(() => {
  void connect(props.ticket)
  void router.isReady().then(() => {
    routeReady.value = true
  }).catch(() => {
    pageFailed.value = true
  })
})
</script>

<template>
  <el-config-provider :locale="zhCn">
    <router-view v-if="state === 'ready'" />
    <ConnectionPage v-else :state="state" />
  </el-config-provider>
</template>
