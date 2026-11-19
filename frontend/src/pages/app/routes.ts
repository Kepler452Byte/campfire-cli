import type { RouteRecordRaw } from "vue-router"

const layout = () => import("./layout/index.vue")
export const routes: RouteRecordRaw[] = [
  { path: "/app", redirect: "/app/scripts", meta: { hidden: true } },
  {
    path: "/app/scripts-menu",
    component: layout,
    redirect: "/app/scripts",
    meta: { title: "Campfire", module: "app" },
    children: [
      { path: "/app/scripts", name: "Scripts", component: () => import("./scripts/index.vue"), meta: { title: "脚本", elIcon: "Folder", keepAlive: true, affix: true } }
    ]
  },
  {
    path: "/app/jobs-menu",
    component: layout,
    redirect: "/app/jobs",
    meta: { title: "Campfire", module: "app" },
    children: [
      { path: "/app/jobs", name: "Jobs", component: () => import("./jobs/index.vue"), meta: { title: "任务", elIcon: "Clock" } },
      { path: "/app/jobs/:id", name: "JobDetail", component: () => import("./jobs/detail.vue"), meta: { title: "任务详情", hidden: true, activeMenu: "/app/jobs" } },
      { path: "/app/jobs/:id/runs/:runId", name: "JobRunLogs", component: () => import("./jobs/logs.vue"), meta: { title: "运行日志", hidden: true, activeMenu: "/app/jobs" } }
    ]
  }
]
