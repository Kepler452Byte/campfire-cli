<script setup lang="ts">
import ErrorLayout from "./components/Layout.vue"
import ErrorImage from "./images/404.svg?component"
</script>

<template>
  <ErrorLayout>
    <ErrorImage aria-hidden="true" />
    <h1>404</h1>
    <p>你访问的页面不存在。</p>
  </ErrorLayout>
</template>
