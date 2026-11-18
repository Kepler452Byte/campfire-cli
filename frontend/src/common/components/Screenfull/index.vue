<script lang="ts" setup>
import screenfull from "screenfull"
import { useAppStore } from "@/pinia/stores/app"

interface Props {
  /** 全屏的元素，默认是 html */
  element?: string
  /** 打开全屏提示语 */
  openTips?: string
  /** 关闭全屏提示语 */
  exitTips?: string
  /** 是否只针对内容区 */
  content?: boolean
}

const { element = "html", openTips = "全屏", exitTips = "退出全屏", content = false } = defineProps<Props>()

const app = useAppStore()
const root = useTemplateRef("root")
const isEnabled = screenfull.isEnabled
const isFullscreen = ref(false)
const isContentLarge = computed(() => app.contentMode === "large")
const fullscreenTips = computed(() => isFullscreen.value ? exitTips : openTips)
const fullscreenSvgName = computed(() => isFullscreen.value ? "fullscreen-exit" : "fullscreen")
const contentLargeTips = computed(() => isContentLarge.value ? "内容区复原" : "内容区放大")
const contentLargeSvgName = computed(() => isContentLarge.value ? "fullscreen-exit" : "fullscreen")
function scope(): HTMLElement | null {
  return root.value?.closest<HTMLElement>(".layout-scope") ?? null
}
function handleFullscreenChange(): void {
  if (!screenfull.isEnabled) return
  isFullscreen.value = screenfull.isFullscreen
  // Only the content controller for this fullscreen element owns its mode.
  if (content && app.contentMode === "full" && screenfull.element !== scope()) app.contentMode = "normal"
}
async function toggleFullscreen(target?: Element): Promise<void> {
  if (!screenfull.isEnabled) {
    ElMessage.warning("您的浏览器无法工作")
    return
  }
  try {
    await screenfull.toggle(target)
  } catch {
    if (content) app.contentMode = "normal"
    ElMessage.warning("无法进入全屏，请重试")
  }
}
function handleFullscreenClick(): void {
  void toggleFullscreen(document.querySelector(element) ?? undefined)
}
function handleContentLargeClick(): void {
  app.contentMode = isContentLarge.value ? "normal" : "large"
}
function handleContentFullClick(): void {
  const target = scope()
  if (!target || !isEnabled) {
    ElMessage.warning("您的浏览器无法工作")
    return
  }
  app.contentMode = "full"
  void toggleFullscreen(target)
}
onMounted(() => {
  if (screenfull.isEnabled) {
    screenfull.on("change", handleFullscreenChange)
    handleFullscreenChange()
  }
})
onBeforeUnmount(() => {
  if (screenfull.isEnabled) {
    screenfull.off("change", handleFullscreenChange)
    if (content && app.contentMode === "full" && screenfull.element === scope()) void screenfull.exit().catch(() => {})
  }
  if (content) app.contentMode = "normal"
})
</script>

<template>
  <div ref="root">
    <!-- 全屏 -->
    <el-tooltip v-if="!content" effect="dark" :content="fullscreenTips" placement="bottom">
      <SvgIcon :name="fullscreenSvgName" @click="handleFullscreenClick" class="svg-icon" />
    </el-tooltip>
    <!-- 内容区 -->
    <el-dropdown v-else :disabled="isFullscreen">
      <SvgIcon :name="contentLargeSvgName" class="svg-icon" />
      <template #dropdown>
        <el-dropdown-menu>
          <!-- 内容区放大 -->
          <el-dropdown-item @click="handleContentLargeClick">
            {{ contentLargeTips }}
          </el-dropdown-item>
          <!-- 内容区全屏 -->
          <el-dropdown-item @click="handleContentFullClick">
            内容区全屏
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<style lang="scss" scoped>
.svg-icon {
  font-size: 20px;
  &:focus {
    outline: none;
  }
}
</style>
