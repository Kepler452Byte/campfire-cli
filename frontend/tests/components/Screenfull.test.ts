import Screenfull from "@@/components/Screenfull/index.vue"
import { flushPromises, mount } from "@vue/test-utils"
import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { nextTick } from "vue"
import { provideLayout } from "@/layouts/context"
import { useAppStore } from "@/pinia/stores/app"

const fullscreen = vi.hoisted(() => ({ isEnabled: true, isFullscreen: false, element: undefined as Element | undefined, toggle: vi.fn(), exit: vi.fn().mockResolvedValue(undefined), listeners: new Set<() => void>() }))
vi.mock("screenfull", () => ({ default: { ...fullscreen, get isFullscreen() {
  return fullscreen.isFullscreen
}, get element() {
  return fullscreen.element
}, on: (_event: string, listener: () => void) => fullscreen.listeners.add(listener), off: (_event: string, listener: () => void) => fullscreen.listeners.delete(listener) } }))

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
  fullscreen.listeners.clear()
  fullscreen.isFullscreen = false
  fullscreen.element = undefined
})
function mountController(content: boolean, id = "admin") {
  return mount({ setup() {
    provideLayout(id)
  }, components: { Screenfull }, template: `<div class="layout-scope"><Screenfull :content="${content}" /></div>` }, {
    global: { stubs: { ElTooltip: { template: "<div><slot /></div>" }, ElDropdown: { template: "<div><slot /><slot name='dropdown' /></div>" }, ElDropdownMenu: { template: "<div><slot /></div>" }, ElDropdownItem: { template: "<button><slot /></button>" }, SvgIcon: true } }
  })
}
describe("全屏状态归属", () => {
  it("普通全屏退出不清理其他布局放大状态，内容全屏退出复原所属实例", async () => {
    const normal = mountController(false)
    const content = mountController(true)
    const other = useAppStore("app")
    other.contentMode = "large"
    const app = useAppStore("admin")
    app.contentMode = "full"
    for (const listener of fullscreen.listeners) listener()
    await nextTick()
    expect(app.contentMode).toBe("normal")
    expect(other.contentMode).toBe("large")
    app.contentMode = "large"
    normal.unmount()
    expect(app.contentMode).toBe("large")
    content.unmount()
    expect(app.contentMode).toBe("normal")
    expect(fullscreen.listeners.size).toBe(0)
  })
  it("请求全屏失败后复原内容模式", async () => {
    fullscreen.toggle.mockRejectedValueOnce(new Error("denied"))
    const wrapper = mountController(true)
    await wrapper.findAll("button")[1]!.trigger("click")
    await flushPromises()
    expect(useAppStore("admin").contentMode).toBe("normal")
    wrapper.unmount()
  })
})
