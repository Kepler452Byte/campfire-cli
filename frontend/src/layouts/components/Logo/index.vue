<script lang="ts" setup>
import ExpandedLogoSvg from "@@/assets/images/layouts/logo-expanded.svg?component"
import LogoSvg from "@@/assets/images/layouts/logo.svg?component"
import { useModuleNavigation } from "@@/composables/use-module-navigation"
import { useLayoutMode } from "@@/composables/useLayoutMode"
import { APP_TITLE } from "@@/constants/app"

interface Props {
  collapse?: boolean
}

const { collapse = true } = defineProps<Props>()
const { isLeft, isTop } = useLayoutMode()
const { home } = useModuleNavigation()
</script>

<template>
  <div class="layout-logo-container" :class="{ 'collapse': collapse, 'is-left': isLeft, 'is-top': isTop }">
    <router-link :to="home" :aria-label="APP_TITLE">
      <transition name="layout-logo-fade">
        <span v-show="collapse" class="logo-layer">
          <LogoSvg class="layout-logo" aria-hidden="true" />
        </span>
      </transition>
      <transition name="layout-logo-fade">
        <span v-show="!collapse" class="logo-layer">
          <ExpandedLogoSvg class="layout-logo-expanded" aria-hidden="true" />
        </span>
      </transition>
    </router-link>
  </div>
</template>

<style lang="scss" scoped>
.layout-logo-container {
  --logo-color: var(--el-text-color-primary);

  position: relative;
  width: 100%;
  height: var(--v3-header-height);
  overflow: hidden;
  color: var(--logo-color);

  &.is-left {
    --logo-color: var(--v3-sidebar-menu-active-text-color);
    &::after {
      content: "";
      position: absolute;
      bottom: 0;
      left: 16px;
      right: 16px;
      height: 1px;
      background: var(--v3-sidebar-divider-color);
    }
  }

  &.is-top {
    height: var(--v3-navigationbar-height);
  }

  > a {
    display: block;
    position: relative;
    width: 100%;
    height: 100%;
    color: inherit;
  }
}

// Crossfade layers overlap so they never compete for layout width.
.logo-layer {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.layout-logo {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
}

.layout-logo-expanded {
  width: calc(var(--v3-sidebar-width) - 24px);
  height: 100%;
  flex-shrink: 0;
}
.layout-logo-fade-enter-active {
  transition: opacity var(--layout-logo-duration) ease-out;
}

.layout-logo-fade-leave-active {
  transition: none;
}
</style>
