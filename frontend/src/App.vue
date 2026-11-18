<script lang="ts" setup>
import { useTheme } from "@@/composables/useTheme"
import zhCn from "element-plus/es/locale/lang/zh-cn" // Element Plus 中文包

const { initTheme } = useTheme()

// 初始化主题
initTheme()
</script>

<template>
  <el-config-provider :locale="zhCn">
    <router-view />
  </el-config-provider>
</template>
