// 统一处理 localStorage

import type { ThemeName } from "@@/composables/useTheme"
import type { SidebarClosed, SidebarOpened } from "@@/constants/app-key"
import { CacheKey } from "@@/constants/cache-key"

// #region 侧边栏状态
export function getSidebarStatus(module = "") {
  return localStorage.getItem(`${CacheKey.SIDEBAR_STATUS}:${module}`)
}

export function setSidebarStatus(sidebarStatus: SidebarOpened | SidebarClosed, module = "") {
  localStorage.setItem(`${CacheKey.SIDEBAR_STATUS}:${module}`, sidebarStatus)
}
// #endregion

// #region 正在应用的主题名称
export function getActiveThemeName() {
  return localStorage.getItem(CacheKey.ACTIVE_THEME_NAME) as ThemeName | null
}

export function setActiveThemeName(themeName: ThemeName) {
  localStorage.setItem(CacheKey.ACTIVE_THEME_NAME, themeName)
}
// #endregion
