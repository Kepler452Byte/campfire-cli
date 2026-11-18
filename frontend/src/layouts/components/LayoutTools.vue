<script setup lang="ts">
import Screenfull from "@@/components/Screenfull/index.vue"
import SearchMenu from "@@/components/SearchMenu/index.vue"
import ThemeSwitch from "@@/components/ThemeSwitch/index.vue"
import { useSettingsStore } from "@/pinia/stores/settings"

const settings = useSettingsStore()
</script>

<template>
  <div class="right-menu">
    <SearchMenu v-if="settings.showSearchMenu" class="right-menu-item" />
    <Screenfull v-if="settings.showScreenfull" class="right-menu-item" />
    <ThemeSwitch v-if="settings.showThemeSwitch" class="right-menu-item" />
  </div>
</template>

<style scoped lang="scss">
.right-menu {
  flex-shrink: 0;
  margin-right: 10px;
  height: 100%;
  display: flex;
  align-items: center;
  gap: 20px;
  .right-menu-item {
    cursor: pointer;
  }
  .account {
    margin-left: 10px;
  }
  @media (max-width: 576px) {
    gap: 12px;
    .account {
      margin-left: 0;
    }
  }
}
</style>
