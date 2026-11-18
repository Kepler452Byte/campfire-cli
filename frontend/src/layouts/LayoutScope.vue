<script lang="ts" setup>
import { useDevice } from "@@/composables/useDevice"
import { useWatermark } from "@@/composables/useWatermark"
import { getModuleId, modules } from "@/modules/navigation"
import { useAppStore } from "@/pinia/stores/app"
import { useSettingsStore } from "@/pinia/stores/settings"
import { useResize } from "./composables/useResize"
import { getLayoutModule, provideLayout } from "./context"
import "@@/assets/styles/sidebar.scss"
import "./transitions.scss"

const { id } = defineProps<{ id: string }>()
provideLayout(id)
// Explicit ID is required here: injection is available to descendants, not this component.
const settings = useSettingsStore(id)
const app = useAppStore(id)
const route = useRoute()
const module = getLayoutModule(id)
if (!app.routePath) app.routePath = modules[module]?.home ?? "/"
watch(() => route.fullPath, (path) => {
  if (getModuleId(route.path) === module) app.routePath = path
}, { immediate: true })
const { isMobile } = useDevice(id)
useResize(id)
const root = useTemplateRef("root")
const { setWatermark, clearWatermark } = useWatermark(root)
watchEffect(() => {
  if (root.value) settings.showWatermark ? setWatermark(import.meta.env.VITE_APP_TITLE) : clearWatermark()
})
onUnmounted(() => {
  clearWatermark()
  app.contentMode = "normal"
})
const mode = computed(() => isMobile.value ? "left" : settings.layoutMode)
</script>

<template>
  <div
    ref="root"
    class="layout-scope"
    :class="{ 'grey-mode': settings.showGreyMode, 'color-weakness': settings.showColorWeakness, 'content-large': app.contentMode === 'large', 'content-full': app.contentMode === 'full' }"
    :data-layout-id="id"
    :data-layout-mode="mode"
    :data-sidebar-style="settings.sidebarStyle"
    :style="{ '--v3-tagsview-height': settings.showTagsView && app.contentMode !== 'full' ? '34px' : '0px' }"
  >
    <slot />
  </div>
</template>

<style scoped lang="scss">
.layout-scope {
  min-height: 100vh;
  --v3-header-height: calc(
    var(--v3-navigationbar-height) + var(--v3-tagsview-height) + var(--v3-header-border-bottom-width)
  );
  --v3-sidebar-menu-item-height: var(--sidebar-item-height);
  &.grey-mode {
    filter: grayscale(1);
  }
  &.color-weakness {
    filter: invert(0.8);
  }
}
</style>

<style lang="scss">
/* Content presentation belongs to this layout, including embedded instances. */
.layout-scope.content-large,
.layout-scope.content-full {
  --v3-navigationbar-height: 0px;
  --v3-sidebar-width: 0px;
  --v3-sidebar-hide-width: 0px;
  --v3-header-border-bottom-width: 0px;
  > .layout-frame > .sidebar-container,
  > .layout-frame > .drawer-bg,
  > .layout-frame > .main-container > .layout-header .navigation-bar,
  > .layout-frame > .main-container > .layout-header > .frame-logo {
    display: none;
  }
}
.layout-scope.content-full {
  background: var(--v3-body-bg-color);
  --v3-header-height: 0px;
  > .layout-frame > .main-container > .layout-header {
    display: none;
  }
}
</style>
