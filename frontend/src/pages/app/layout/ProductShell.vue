<script setup lang="ts">
import StandardHeader from "@/layouts/StandardHeader.vue"
import StandardShell from "@/layouts/StandardShell.vue"
</script>

<template>
  <StandardShell class="app-layout list-layout">
    <template #header>
      <StandardHeader />
    </template>
  </StandardShell>
</template>
