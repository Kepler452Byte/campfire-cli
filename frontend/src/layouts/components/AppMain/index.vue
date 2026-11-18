<script lang="ts" setup>
import Footer from "@/layouts/components/Footer/index.vue"
import { useSettingsStore } from "@/pinia/stores/settings"
import { useTagsViewStore } from "@/pinia/stores/tags-view"

const tagsViewStore = useTagsViewStore()

const settingsStore = useSettingsStore()
const scrollbarId = useId()
</script>

<template>
  <section class="app-main">
    <div :id="scrollbarId" class="app-scrollbar">
      <!-- key 采用 route.path 和 route.fullPath 有着不同的效果，大多数时候 path 更通用 -->
      <router-view v-slot="{ Component, route }">
        <keep-alive :include="tagsViewStore.cachedViews">
          <component :is="Component" :key="route.path" class="app-container-grow" />
        </keep-alive>
      </router-view>
      <!-- 页脚 -->
      <Footer v-if="settingsStore.showFooter" />
    </div>
    <!-- 返回顶部 -->
    <el-backtop />
    <!-- 返回顶部（固定 Header 情况下） -->
    <el-backtop :target="`#${scrollbarId}`" />
  </section>
</template>

<style lang="scss" scoped>
@import "@@/assets/styles/mixins.scss";

.app-main {
  width: 100%;
  display: flex;
}

.app-scrollbar {
  flex-grow: 1;
  overflow: auto;
  @extend %scrollbar;
  display: flex;
  flex-direction: column;
  .app-container-grow {
    flex-grow: 1;
  }
}
</style>
