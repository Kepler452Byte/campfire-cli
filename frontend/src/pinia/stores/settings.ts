import { getLayoutsConfig, setLayoutsConfig } from "@/layouts/cache"
import { getModuleLayoutsConfig } from "@/layouts/config"
import { getLayoutModule, useLayoutId } from "@/layouts/context"

export function useSettingsStore(id = useLayoutId()) {
  return defineStore(`layout:${id}:settings`, () => {
    const state = reactive({ ...getModuleLayoutsConfig(getLayoutModule(id)), ...getLayoutsConfig(id) })
    watch(state, settings => setLayoutsConfig(settings, id), { deep: true, flush: "sync" })
    return { ...toRefs(state) }
  })()
}
