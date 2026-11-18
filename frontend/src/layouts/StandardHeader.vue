<script setup lang="ts">
import { useDevice } from "@@/composables/useDevice"
import { useLayoutMode } from "@@/composables/useLayoutMode"
import Breadcrumb from "@/layouts/components/Breadcrumb/index.vue"
import Hamburger from "@/layouts/components/Hamburger/index.vue"
import LayoutTools from "@/layouts/components/LayoutTools.vue"
import Sidebar from "@/layouts/components/Sidebar/index.vue"
import { useAppStore } from "@/pinia/stores/app"

const app = useAppStore()
const { isMobile } = useDevice()
const { isTop } = useLayoutMode()
</script>

<template>
  <div class="navigation-bar product-header">
    <Hamburger v-if="!isTop || isMobile" :is-active="app.sidebar.opened" class="hamburger" @toggle-click="app.toggleSidebar(false)" />
    <Sidebar v-if="isTop && !isMobile" class="sidebar" />
    <Breadcrumb v-else class="breadcrumb" />
    <slot />
    <LayoutTools />
  </div>
</template>

<style scoped lang="scss">
.product-header {
  display: flex;
  align-items: center;
  height: var(--v3-navigationbar-height);
  color: var(--v3-navigationbar-text-color);
  overflow: visible;
}
.hamburger {
  padding: 0 15px;
  height: 100%;
  display: flex;
  align-items: center;
  cursor: pointer;
}
.breadcrumb,
.sidebar {
  flex: 1;
  min-width: 0;
}
.breadcrumb {
  @media (max-width: 576px) {
    display: none;
  }
}
</style>
