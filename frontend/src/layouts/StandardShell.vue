<script setup lang="ts">
import AppMain from "@/layouts/components/AppMain/index.vue"
import Logo from "@/layouts/components/Logo/index.vue"
import RightPanel from "@/layouts/components/RightPanel/index.vue"
import Settings from "@/layouts/components/Settings/index.vue"
import Sidebar from "@/layouts/components/Sidebar/index.vue"
import TagsView from "@/layouts/components/TagsView/index.vue"
import LayoutFrame from "@/layouts/LayoutFrame.vue"
import { useSettingsStore } from "@/pinia/stores/settings"
import StandardHeader from "./StandardHeader.vue"

defineOptions({ inheritAttrs: false })

const settings = useSettingsStore()
</script>

<template>
  <LayoutFrame class="standard-layout" v-bind="$attrs">
    <template #logo>
      <Logo v-if="settings.showLogo" :collapse="false" />
    </template>
    <template #sidebar>
      <slot name="sidebar">
        <Sidebar />
      </slot>
    </template>
    <template #header>
      <slot name="header">
        <StandardHeader />
      </slot>
    </template>
    <template #tags>
      <TagsView v-if="settings.showTagsView" />
    </template>
    <template #main>
      <AppMain />
    </template>
  </LayoutFrame>
  <RightPanel v-if="settings.showSettings">
    <Settings />
  </RightPanel>
</template>
