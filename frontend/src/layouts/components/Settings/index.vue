<script lang="ts" setup>
import { useLayoutMode } from "@@/composables/useLayoutMode"
import { Refresh } from "@element-plus/icons-vue"
import { removeLayoutsConfig } from "@/layouts/cache"
import { useLayoutId } from "@/layouts/context"
import { sidebarStyles } from "@/layouts/sidebar-style"
import { useSettingsStore } from "@/pinia/stores/settings"
import SelectLayoutMode from "./SelectLayoutMode.vue"

const { isLeft } = useLayoutMode()

const settingsStore = useSettingsStore()
const layoutId = useLayoutId()

// 使用 storeToRefs 将提取的属性保持其响应性
const {
  sidebarStyle,
  showTagsView,
  showLogo,
  fixedHeader,
  showFooter,
  showNotify,
  showThemeSwitch,
  showScreenfull,
  showSearchMenu,
  cacheTagsView,
  showWatermark,
  showGreyMode,
  showColorWeakness
} = storeToRefs(settingsStore)

/** 定义 switch 设置项 */
const switchSettings = {
  "显示标签栏": showTagsView,
  "显示 Logo": showLogo,
  "固定 Header": fixedHeader,
  "显示页脚": showFooter,
  "显示消息通知": showNotify,
  "显示切换主题按钮": showThemeSwitch,
  "显示全屏按钮": showScreenfull,
  "显示搜索按钮": showSearchMenu,
  "是否缓存标签栏": cacheTagsView,
  "开启系统水印": showWatermark,
  "显示灰色模式": showGreyMode,
  "显示色弱模式": showColorWeakness
}

// 非左侧模式时，Header 都是 fixed 布局
watchEffect(() => {
  !isLeft.value && (fixedHeader.value = true)
})

/** 重置项目配置 */
function resetLayoutsConfig() {
  removeLayoutsConfig(layoutId)
  location.reload()
}
</script>

<template>
  <div class="setting-container">
    <h4>布局配置</h4>
    <SelectLayoutMode />
    <div class="setting-item">
      <span class="setting-name">侧边栏样式</span>
      <el-select v-model="sidebarStyle" aria-label="侧边栏样式" style="width: 110px">
        <el-option v-for="item in sidebarStyles" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
    </div>
    <el-divider />
    <h4>功能配置</h4>
    <div v-for="(settingValue, settingName, index) in switchSettings" :key="index" class="setting-item">
      <span class="setting-name">{{ settingName }}</span>
      <el-switch v-model="settingValue.value" :disabled="!isLeft && settingName === '固定 Header'" />
    </div>
    <el-button type="danger" :icon="Refresh" @click="resetLayoutsConfig">
      重 置
    </el-button>
  </div>
</template>

<style lang="scss" scoped>
@import "@@/assets/styles/mixins.scss";

.setting-container {
  padding: 20px;
  .setting-item {
    font-size: 14px;
    color: var(--el-text-color-regular);
    padding: 5px 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    .setting-name {
      @extend %ellipsis;
    }
  }
  .el-button {
    margin-top: 40px;
    width: 100%;
  }
}
</style>
