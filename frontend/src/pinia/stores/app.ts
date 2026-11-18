import { DeviceEnum, SIDEBAR_CLOSED, SIDEBAR_OPENED } from "@@/constants/app-key"
import { getSidebarStatus, setSidebarStatus } from "@@/utils/cache/local-storage"
import { useLayoutId } from "@/layouts/context"

interface Sidebar {
  opened: boolean
  withoutAnimation: boolean
}

/** 设置侧边栏状态本地缓存 */
function handleSidebarStatus(opened: boolean, module: string) {
  opened ? setSidebarStatus(SIDEBAR_OPENED, module) : setSidebarStatus(SIDEBAR_CLOSED, module)
}

export function useAppStore(id = useLayoutId()) {
  return defineStore(`layout:${id}:app`, () => {
  // 侧边栏状态
    const sidebar: Sidebar = reactive({
      opened: getSidebarStatus(id) !== SIDEBAR_CLOSED,
      withoutAnimation: false
    })

    // 设备类型
    const device = ref<DeviceEnum>(DeviceEnum.Desktop)
    const routePath = ref("")
    const contentMode = ref<"normal" | "large" | "full">("normal")

    // 监听侧边栏 opened 状态
    watch(
      () => sidebar.opened,
      (opened) => {
        handleSidebarStatus(opened, id)
      },
      { flush: "sync" }
    )

    // 切换侧边栏
    const toggleSidebar = (withoutAnimation: boolean) => {
      sidebar.opened = !sidebar.opened
      sidebar.withoutAnimation = withoutAnimation
    }

    // 关闭侧边栏
    const closeSidebar = (withoutAnimation: boolean) => {
      sidebar.opened = false
      sidebar.withoutAnimation = withoutAnimation
    }

    // 切换设备类型
    const toggleDevice = (value: DeviceEnum) => {
      device.value = value
    }

    return { device, routePath, contentMode, sidebar, toggleSidebar, closeSidebar, toggleDevice }
  })()
}
