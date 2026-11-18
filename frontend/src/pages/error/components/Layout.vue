<script setup lang="ts">
import { getRootTarget } from "@/modules/navigation"
</script>

<template>
  <main class="error">
    <div class="error-content">
      <slot />
    </div>
    <RouterLink :to="getRootTarget()">
      <el-button type="primary">
        返回首页
      </el-button>
    </RouterLink>
  </main>
</template>

<style scoped lang="scss">
.error {
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 24px;
  padding: 24px;
  text-align: center;
}
.error-content {
  max-width: 400px;
  width: 100%;
}
.error-content :deep(svg) {
  width: 100%;
  height: auto;
}
</style>
