<script lang="ts" setup>
import { Expand, Fold } from "@element-plus/icons-vue"

interface Props {
  isActive?: boolean
}

const { isActive = false } = defineProps<Props>()

const emit = defineEmits<{
  toggleClick: []
}>()

function toggleClick() {
  emit("toggleClick")
}
</script>

<template>
  <button type="button" aria-label="切换侧栏" :aria-expanded="isActive" @click="toggleClick">
    <el-icon :size="20" class="icon">
      <Fold v-if="isActive" />
      <Expand v-else />
    </el-icon>
  </button>
</template>

<style lang="scss" scoped>
button {
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
}
.icon {
  vertical-align: middle;
  color: var(--v3-hamburger-text-color);
}
</style>
