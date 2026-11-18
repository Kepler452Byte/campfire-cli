import { DeviceEnum } from "@@/constants/app-key"
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it } from "vitest"
import { getVisitedViews, setVisitedViews } from "@/layouts/cache"
import { modules } from "@/modules/navigation"
import { useAppStore } from "@/pinia/stores/app"
import { useSettingsStore } from "@/pinia/stores/settings"
import { clearLayoutSessions, useTagsViewStore } from "@/pinia/stores/tags-view"

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
})

const ids = Object.keys(modules).filter(id => modules[id]!.enabled)
describe("独立布局实例", () => {
  it("同时存在的模块与嵌入布局独立持有侧栏、设备、设置和标签", () => {
    if (!ids.length) return
    const first = ids[0]!
    const second = ids[1] ?? `${first}:embedded`
    const firstShell = useAppStore(first)
    const secondShell = useAppStore(second)
    const firstSettings = useSettingsStore(first)
    const secondSettings = useSettingsStore(second)
    const original = secondSettings.showTagsView
    firstSettings.showTagsView = !original
    firstShell.toggleSidebar(false)
    firstShell.toggleDevice(DeviceEnum.Mobile)
    firstShell.routePath = modules[first]!.home
    expect(secondShell.routePath).toBe("")
    const firstTags = useTagsViewStore(first)
    firstTags.addVisitedView({ path: modules[first]!.home, name: "FirstPage" })
    expect(secondShell.device).toBe(DeviceEnum.Desktop)
    expect(secondShell.sidebar.opened).toBe(true)
    expect(secondSettings.showTagsView).toBe(original)
    expect(useTagsViewStore(second).visitedViews).toEqual([])
    expect(useAppStore(first)).toBe(firstShell)
    expect(useTagsViewStore(first).visitedViews.map(view => view.name)).toEqual(["FirstPage"])
    const embedded = useAppStore(`${first}:embedded`)
    expect(embedded).not.toBe(firstShell)
    expect(embedded.sidebar.opened).toBe(true)
  })

  it("刷新恢复各实例配置与缓存，认证失效清理所有会话", () => {
    if (!ids.length) return
    const instances = [...ids, `${ids[0]}:embedded`]
    for (const [index, id] of instances.entries()) {
      const module = id.split(":")[0]!
      const settings = useSettingsStore(id)
      settings.showTagsView = index % 2 === 0
      settings.cacheTagsView = true
      const tags = useTagsViewStore(id)
      const view = { path: modules[module]!.home, name: `Page${id}`, meta: { keepAlive: true } }
      tags.addVisitedView(view)
      tags.addCachedView(view)
    }
    setActivePinia(createPinia())
    for (const [index, id] of instances.entries()) {
      expect(useSettingsStore(id).showTagsView).toBe(index % 2 === 0)
      expect(useTagsViewStore(id).cachedViews).toEqual([`Page${id}`])
    }
    setVisitedViews([{ name: "OldEmbeddedUser" }], `${ids[0]}:not-mounted`)
    clearLayoutSessions()
    expect(getVisitedViews(`${ids[0]}:not-mounted`)).toEqual([])
    for (const id of instances) {
      expect(useAppStore(id).routePath).toBe("")
      expect(useTagsViewStore(id).visitedViews).toEqual([])
      expect(useTagsViewStore(id).cachedViews).toEqual([])
    }
  })
})

describe("动态标签标题", () => {
  it("按 path 更新并保留 query、缓存与实例隔离，不修改原路由 meta", () => {
    if (!modules.app?.enabled) return
    const settings = useSettingsStore("app")
    settings.cacheTagsView = true
    const tags = useTagsViewStore("app")
    const meta = { title: "账户", keepAlive: true }
    tags.addVisitedView({ path: "/app/account", fullPath: "/app/account?a=1", name: "ProductAccount", meta })
    tags.addCachedView({ path: "/app/account", name: "ProductAccount", meta })
    const other = useTagsViewStore("app:embedded")
    other.addVisitedView({ path: "/app/account", meta })
    tags.setVisitedTitle("/app/account", "账户 · Alice")
    tags.setVisitedTitle("/app/missing", "忽略")
    tags.setVisitedTitle("/app/account", "  ")
    expect(meta.title).toBe("账户")
    expect(other.visitedViews[0]?.meta?.title).toBe("账户")
    tags.addVisitedView({ path: "/app/account", fullPath: "/app/account?a=2", name: "ProductAccount", query: { a: "2" }, meta })
    expect(tags.visitedViews).toHaveLength(1)
    expect(tags.visitedViews[0]?.meta?.title).toBe("账户 · Alice")
    expect(tags.visitedViews[0]?.query).toEqual({ a: "2" })
    setActivePinia(createPinia())
    expect(useTagsViewStore("app").visitedViews[0]?.meta?.title).toBe("账户 · Alice")
    expect(useTagsViewStore("app").cachedViews).toEqual(["ProductAccount"])
  })
})
