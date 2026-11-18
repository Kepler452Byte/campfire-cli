import { getLayoutModule, useLayoutId } from "@/layouts/context"
import { modules } from "@/modules/navigation"
import { constantRoutes } from "@/router"

export function useModuleNavigation() {
  const layoutId = useLayoutId()
  const currentModule = computed(() => getLayoutModule(layoutId))
  const home = computed(() => modules[currentModule.value]?.home ?? "/app/jobs")
  const menus = computed(() => constantRoutes.filter(route => route.meta?.module === currentModule.value && !route.meta?.hidden))
  return { currentModule, home, menus }
}
