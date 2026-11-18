<script lang="ts" setup>
import { useModuleNavigation } from "@@/composables/use-module-navigation"
import { useDevice } from "@@/composables/useDevice"
import { useLayoutMode } from "@@/composables/useLayoutMode"
import Logo from "@/layouts/components/Logo/index.vue"
import { useAppStore } from "@/pinia/stores/app"
import { useSettingsStore } from "@/pinia/stores/settings"
import Item from "./Item.vue"

const { isMobile } = useDevice()
const { isLeft, isTop } = useLayoutMode()
const route = useRoute()
const appStore = useAppStore()
const { menus: noHiddenRoutes } = useModuleNavigation()
const settingsStore = useSettingsStore()
const activeMenu = computed(() => appStore.routePath === route.fullPath ? route.meta.activeMenu || route.path : appStore.routePath.split(/[?#]/)[0])
const isCollapse = computed(() => !appStore.sidebar.opened)
const isLogo = computed(() => (isLeft.value || isMobile.value) && settingsStore.showLogo)
const isVertical = computed(() => !isTop.value || isMobile.value)
</script>

<template>
  <div :class="{ 'has-logo': isLogo, 'sidebar-vertical': isVertical }">
    <Logo v-if="isLogo" :collapse="isCollapse" />
    <el-scrollbar wrap-class="scrollbar-wrapper">
      <el-menu
        :default-active="activeMenu"
        :collapse="isCollapse && !isTop"
        :collapse-transition="false"
        :mode="isTop && !isMobile ? 'horizontal' : 'vertical'"
      >
        <Item v-for="noHiddenRoute in noHiddenRoutes" :key="noHiddenRoute.path" :item="noHiddenRoute" :base-path="noHiddenRoute.path" />
      </el-menu>
    </el-scrollbar>
  </div>
</template>

<style lang="scss" scoped>
.has-logo .el-scrollbar {
  height: calc(100% - var(--v3-header-height));
}
.el-scrollbar {
  height: 100%;
  :deep(.scrollbar-wrapper) {
    overflow-x: hidden;
  }
  :deep(.el-scrollbar__bar.is-horizontal) {
    display: none;
  }
}
.el-menu {
  user-select: none;
  border: none;
  width: 100%;
}
.sidebar-vertical {
  --el-menu-bg-color: var(--v3-sidebar-menu-bg-color);
  --el-menu-text-color: var(--v3-sidebar-menu-text-color);
  --el-menu-active-color: var(--v3-sidebar-menu-active-text-color);
  --el-menu-hover-bg-color: var(--v3-sidebar-menu-hover-bg-color);
  --el-menu-item-height: var(--v3-sidebar-menu-item-height);
  --el-menu-sub-item-height: var(--v3-sidebar-menu-item-height);
  --el-menu-base-level-padding: 16px;
  --el-menu-level-padding: 12px;
  background: var(--v3-sidebar-menu-bg-color);

  .el-menu:not(.el-menu--collapse) {
    padding: 16px var(--sidebar-inset);
  }
  .el-menu--collapse {
    padding: 16px 6px;

    // 收起后可用宽度已扣除菜单留白，不能继续使用展开态的图标间距。
    :deep(.el-sub-menu__title),
    :deep(.el-menu-item),
    :deep(.el-menu-tooltip__trigger) {
      padding: 0;
      display: flex;
      justify-content: center;
    }
    :deep(.el-icon),
    :deep(.svg-icon) {
      margin-right: 0 !important;
      flex-shrink: 0;
    }
  }
  :deep(.el-menu-item),
  :deep(.el-sub-menu__title) {
    border-radius: var(--sidebar-radius);
    margin-bottom: 4px;
    transition:
      background-color 0.15s,
      color 0.15s;
    &:hover {
      color: var(--v3-sidebar-menu-hover-text-color);
    }
  }
  :deep(.el-sub-menu + .el-sub-menu) {
    margin-top: var(--sidebar-group-gap);
  }
  :deep(.el-sub-menu .el-menu) {
    padding: 0;
  }
  :deep(.el-menu-item.is-active) {
    background: var(--v3-sidebar-menu-selected-bg-color);
    color: var(--v3-sidebar-menu-active-text-color);
    font-weight: 500;
    &::before {
      content: "";
      position: absolute;
      inset: 0 auto 0 0;
      width: var(--sidebar-marker-width);
      background: var(--v3-sidebar-menu-active-text-color);
    }
    &:hover {
      background: var(--v3-sidebar-menu-selected-hover-bg-color);
    }
  }
  :deep(.el-sub-menu.is-active > .el-sub-menu__title) {
    color: var(--v3-sidebar-menu-hover-text-color);
  }
  .el-menu--collapse :deep(.el-sub-menu.is-active > .el-sub-menu__title) {
    color: var(--v3-sidebar-menu-active-text-color);
    background: var(--v3-sidebar-menu-selected-bg-color);
    &::before {
      content: "";
      position: absolute;
      inset: 0 auto 0 0;
      width: var(--sidebar-marker-width);
      background: var(--v3-sidebar-menu-active-text-color);
    }
  }
  :deep(.el-menu-item:focus-visible),
  :deep(.el-sub-menu__title:focus-visible) {
    outline: 2px solid var(--v3-sidebar-menu-active-text-color);
    outline-offset: -2px;
  }
}
</style>
