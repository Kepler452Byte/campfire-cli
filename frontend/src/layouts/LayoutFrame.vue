<script setup lang="ts">
import { useDevice } from "@@/composables/useDevice"
import { useAppStore } from "@/pinia/stores/app"
import { useSettingsStore } from "@/pinia/stores/settings"

const app = useAppStore()
const settings = useSettingsStore()
const { isMobile } = useDevice()
const mode = computed(() => isMobile.value ? "left" : settings.layoutMode)
</script>

<template>
  <div
    :key="mode"
    @keydown.esc="isMobile && app.sidebar.opened && app.closeSidebar(false)"
    class="layout-frame app-wrapper"
    :data-mode="mode"
    :class="{ hideSidebar: !app.sidebar.opened, openSidebar: app.sidebar.opened, withoutAnimation: app.sidebar.withoutAnimation, mobile: isMobile, hasTagsView: settings.showTagsView, fixedHeader: settings.fixedHeader }"
  >
    <div v-if="isMobile && app.sidebar.opened" class="drawer-bg" @click="app.closeSidebar(false)" />
    <aside v-if="mode !== 'top'" class="sidebar-container">
      <slot name="sidebar" />
    </aside>
    <div class="main-container">
      <header class="layout-header" :class="{ 'fixed-header': settings.fixedHeader || mode !== 'left' }">
        <div v-if="mode !== 'left'" class="frame-logo">
          <slot name="logo" />
        </div>
        <div class="header-content">
          <slot name="header" /><slot name="tags" />
        </div>
      </header>
      <slot name="main" />
    </div>
  </div>
</template>

<style scoped lang="scss">
.layout-frame {
  min-height: 100vh;
  width: 100%;
  position: relative;
  --frame-sidebar-width: var(--v3-sidebar-width);
  &.hideSidebar {
    --frame-sidebar-width: var(--v3-sidebar-hide-width);
  }
}
.sidebar-container {
  position: fixed;
  inset: 0 auto 0 0;
  width: var(--frame-sidebar-width);
  height: 100vh;
  z-index: 1001;
  background: var(--v3-sidebar-menu-bg-color);
  border-right: var(--v3-sidebar-border-right);
  transition: width var(--layout-sidebar-duration);
  // Popups mounted inside this scope must remain visible outside the sidebar.
  overflow: visible;
}
.main-container {
  margin-left: var(--frame-sidebar-width);
  transition: margin-left var(--layout-sidebar-duration);
}
.layout-header {
  position: relative;
  z-index: 1002;
  display: flex;
  background: var(--v3-header-bg-color);
  box-shadow: var(--v3-header-box-shadow);
  border-bottom: var(--v3-header-border-bottom);
}
.header-content {
  flex: 1;
  min-width: 0;
}
.fixed-header {
  position: fixed;
  top: 0;
  right: 0;
  width: calc(100% - var(--frame-sidebar-width));
  transition: width var(--layout-sidebar-duration);
}
.frame-logo {
  flex: 0 0 var(--v3-sidebar-width);
}
:deep(.app-main) {
  min-height: calc(100vh - var(--v3-header-height));
  overflow: hidden;
}
.fixed-header + :deep(.app-main) {
  padding-top: var(--v3-header-height);
  height: 100vh;
}
[data-mode="top"],
[data-mode="left-top"] {
  .main-container {
    margin-left: 0;
  }
  .fixed-header {
    width: 100%;
  }
  :deep(.app-main) {
    padding-top: var(--v3-header-height);
    height: 100vh;
  }
}
[data-mode="left-top"] {
  .sidebar-container {
    padding-top: var(--v3-header-height);
  }
  :deep(.app-main) {
    padding-left: var(--frame-sidebar-width);
    transition: padding-left var(--layout-sidebar-duration);
  }
}
.drawer-bg {
  position: fixed;
  inset: 0;
  background: rgb(0 0 0 / 30%);
  z-index: 1000;
}
.layout-frame.mobile {
  --frame-sidebar-width: 0px;
  // The mobile drawer and its backdrop must cover the fixed header as well.
  .drawer-bg {
    z-index: 1003;
  }
  .sidebar-container {
    z-index: 1004;
  }
  .main-container,
  .fixed-header {
    transition: none;
  }
  .sidebar-container {
    width: var(--v3-sidebar-width);
    // Entering the mobile breakpoint is an immediate state change. Only animate user actions.
    transition: none;
  }
  &:not(.withoutAnimation) .sidebar-container {
    transition: transform var(--layout-sidebar-duration);
  }
  &.hideSidebar .sidebar-container {
    pointer-events: none;
    transform: translateX(-100%);
  }
  .frame-logo {
    display: none;
  }
}
.withoutAnimation {
  .sidebar-container,
  .main-container,
  .fixed-header {
    transition: none;
  }
}
</style>
