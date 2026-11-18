<script lang="ts" setup>
import logoUrl from "@@/assets/images/layouts/logo.svg?url"
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
          <img :src="logoUrl" class="layout-logo" alt="">
        </span>
      </transition>
      <transition name="layout-logo-fade">
        <span v-show="!collapse" class="logo-layer logo-brand">
          <img :src="logoUrl" class="layout-logo-expanded" alt="">
          <span class="logo-title">{{ APP_TITLE }}</span>
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
    --logo-color: var(--v3-sidebar-menu-hover-text-color);
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
  width: 40px;
  height: 40px;
  flex-shrink: 0;
}

.layout-logo-expanded {
  width: 48px;
  height: 48px;
  flex-shrink: 0;
}
.logo-brand {
  gap: 4px;
  white-space: nowrap;
}
.logo-title {
  font-size: 23px;
  font-weight: 700;
  letter-spacing: -0.4px;
}
.layout-logo-fade-enter-active {
  transition: opacity var(--layout-logo-duration) ease-out;
}

.layout-logo-fade-leave-active {
  transition: none;
}
</style>
