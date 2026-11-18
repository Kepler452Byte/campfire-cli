<script lang="ts" setup>
import Modal from "./Modal.vue"

/** 控制 modal 显隐 */
const visible = ref<boolean>(false)

/** 打开 modal */
function handleOpen() {
  visible.value = true
}
</script>

<template>
  <div>
    <el-tooltip effect="dark" content="搜索菜单" placement="bottom">
      <button type="button" class="search-trigger" aria-label="搜索菜单" @click="handleOpen">
        <SvgIcon name="search" class="svg-icon" />
      </button>
    </el-tooltip>
    <Modal v-model="visible" />
  </div>
</template>

<style lang="scss" scoped>
.search-trigger {
  display: inline-flex;
  padding: 0;
  background: transparent;
  border: none;
  color: inherit;
  cursor: pointer;
  &:focus-visible {
    outline: 2px solid var(--el-color-primary);
    outline-offset: 4px;
  }
}
.svg-icon {
  font-size: 20px;
  &:focus {
    outline: none;
  }
}
</style>
