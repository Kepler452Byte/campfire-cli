import type { RouteRecordRaw } from "vue-router"
import { setRouteChange } from "@@/composables/useRouteListener"
import { useTitle } from "@@/composables/useTitle"
import { createRouter, createWebHistory } from "vue-router"
import { routes as appRoutes } from "@/pages/app/routes"

export const constantRoutes: RouteRecordRaw[] = [
  { path: "/", redirect: "/app/jobs", meta: { hidden: true } },
  ...appRoutes,
  { path: "/redirect/:path(.*)", component: () => import("@/pages/redirect/index.vue"), meta: { hidden: true } },
  { path: "/:pathMatch(.*)*", component: () => import("@/pages/error/404.vue"), meta: { hidden: true } }
]
export const router = createRouter({ history: createWebHistory(), routes: constantRoutes })
const { setTitle } = useTitle()
router.afterEach((to) => {
  setTitle(to.meta.title)
  setRouteChange(to)
})
