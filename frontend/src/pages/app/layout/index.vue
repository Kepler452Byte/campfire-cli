<script setup lang="ts">
import LayoutScope from "@/layouts/LayoutScope.vue"
import ProductShell from "./ProductShell.vue"

const { instanceId = "app" } = defineProps<{ instanceId?: string }>()
</script>

<template>
  <LayoutScope :id="instanceId">
    <ProductShell />
  </LayoutScope>
</template>
