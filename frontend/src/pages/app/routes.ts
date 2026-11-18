import type { RouteRecordRaw } from "vue-router"

export const routes: RouteRecordRaw[] = [{
  path: "/app",
  name: "ProductApp",
  component: () => import("./layout/index.vue"),
  redirect: "/app/jobs",
  meta: { title: "Campfire", module: "app", elIcon: "Grid" },
  children: [
    { path: "jobs", name: "Jobs", component: () => import("./jobs/index.vue"), meta: { title: "定时任务", elIcon: "Clock", affix: true } },
    { path: "jobs/:id", name: "JobDetail", component: () => import("./jobs/detail.vue"), meta: { title: "任务详情", hidden: true, activeMenu: "/app/jobs" } },
    { path: "jobs/:id/runs/:runId", name: "JobRunLogs", component: () => import("./jobs/logs.vue"), meta: { title: "运行日志", hidden: true, activeMenu: "/app/jobs" } }
  ]
}]
