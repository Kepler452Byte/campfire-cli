<script setup lang="ts">
import ErrorLayout from "./components/Layout.vue"
import ErrorImage from "./images/403.svg?component"
</script>

<template>
  <ErrorLayout>
    <ErrorImage aria-hidden="true" />
    <h1>403</h1>
    <p>你没有权限访问此页面，请联系管理员或退出后切换账户。</p>
  </ErrorLayout>
</template>
