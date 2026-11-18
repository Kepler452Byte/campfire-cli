import type { Pinia } from "pinia"
import type { RouteLocationNormalizedGeneric } from "vue-router"
import { CacheKey } from "@@/constants/cache-key"
import { getCachedViews, getVisitedViews, setCachedViews, setVisitedViews } from "@/layouts/cache"
import { getLayoutModule, useLayoutId } from "@/layouts/context"
import { enabledModules, getModuleId } from "@/modules/navigation"
import { useAppStore } from "./app"
import { useSettingsStore } from "./settings"

export type TagView = Partial<RouteLocationNormalizedGeneric>

const layoutInstances = new Set<string>()

export function useTagsViewStore(id = useLayoutId(), instance?: Pinia) {
  layoutInstances.add(id)
  return defineStore(`layout:${id}:tags`, () => {
    const settings = useSettingsStore(id)
    const moduleId = getLayoutModule(id)
    const visitedViews = ref<TagView[]>(settings.cacheTagsView ? getVisitedViews(id).filter(view => !!view.path && getModuleId(view.path) === moduleId) : [])
    const names = new Set(visitedViews.value.map(view => view.name))
    const cachedViews = ref<string[]>(settings.cacheTagsView ? getCachedViews(id).filter(name => names.has(name)) : [])

    watch([visitedViews, cachedViews, () => settings.cacheTagsView], () => {
      setVisitedViews(settings.cacheTagsView ? visitedViews.value : [], id)
      setCachedViews(settings.cacheTagsView ? cachedViews.value : [], id)
    }, { deep: true, flush: "sync" })

    function clearSession(): void {
      visitedViews.value = []
      cachedViews.value = []
      setVisitedViews([], id)
      setCachedViews([], id)
    }

    // #region add
    const addVisitedView = (view: TagView) => {
      if (!view.path || getModuleId(view.path) !== moduleId) return
      // 检查是否已经存在相同的 visitedView
      const index = visitedViews.value.findIndex(v => v.path === view.path)
      if (index !== -1) {
      // 防止 query 参数丢失
        visitedViews.value[index].fullPath !== view.fullPath && (visitedViews.value[index] = { ...view, meta: { ...view.meta, title: visitedViews.value[index]?.meta?.title ?? view.meta?.title } })
      } else {
      // 添加新的 visitedView
        visitedViews.value.push({ ...view })
      }
    }

    /** Tags use path identity; query changes update the same visited tab. */
    function setVisitedTitle(path: string, title: string): void {
      const view = visitedViews.value.find(view => view.path === path)
      if (!view || !title.trim()) return
      view.meta = { ...view.meta, title }
    }

    const addCachedView = (view: TagView) => {
      if (!view.path || getModuleId(view.path) !== moduleId) return
      if (typeof view.name !== "string") return
      if (cachedViews.value.includes(view.name)) return
      if (view.meta?.keepAlive) {
        cachedViews.value.push(view.name)
      }
    }
    // #endregion

    // #region del
    const delVisitedView = (view: TagView) => {
      const index = visitedViews.value.findIndex(v => v.path === view.path)
      if (index !== -1) {
        visitedViews.value.splice(index, 1)
      }
    }

    const delCachedView = (view: TagView) => {
      if (typeof view.name !== "string") return
      const index = cachedViews.value.indexOf(view.name)
      if (index !== -1) {
        cachedViews.value.splice(index, 1)
      }
    }
    // #endregion

    // #region delOthers
    const delOthersVisitedViews = (view: TagView) => {
      visitedViews.value = visitedViews.value.filter((v) => {
        return v.meta?.affix || v.path === view.path
      })
    }

    const delOthersCachedViews = (view: TagView) => {
      if (typeof view.name !== "string") return
      const index = cachedViews.value.indexOf(view.name)
      if (index !== -1) {
        cachedViews.value = cachedViews.value.slice(index, index + 1)
      } else {
      // 如果 index = -1, 没有缓存的 tags
        cachedViews.value = []
      }
    }
    // #endregion

    // #region delAll
    const delAllVisitedViews = () => {
    // 保留固定的 tags
      visitedViews.value = visitedViews.value.filter(tag => tag.meta?.affix)
    }

    const delAllCachedViews = () => {
      cachedViews.value = []
    }
    // #endregion

    return {
      setVisitedTitle,
      clearSession,
      visitedViews,
      cachedViews,
      addVisitedView,
      addCachedView,
      delVisitedView,
      delCachedView,
      delOthersVisitedViews,
      delOthersCachedViews,
      delAllVisitedViews,
      delAllCachedViews
    }
  })(instance)
}

/** Clear every mounted or persisted layout session. */
export function clearLayoutSessions(instance?: Pinia): void {
  for (const [id] of enabledModules) layoutInstances.add(id)
  for (const id of layoutInstances) {
    useTagsViewStore(id, instance).clearSession()
    useAppStore(id).routePath = ""
    useAppStore(id).contentMode = "normal"
  }
  // Include persisted embedded layouts that have not mounted in this session.
  const keys = Array.from({ length: localStorage.length }, (_, index) => localStorage.key(index))
  for (const key of keys) {
    if (key?.startsWith(`${CacheKey.VISITED_VIEWS}:`) || key?.startsWith(`${CacheKey.CACHED_VIEWS}:`)) localStorage.removeItem(key)
  }
}
