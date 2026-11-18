import type { SidebarStyle } from "./sidebar-style"
import { LayoutModeEnum } from "@@/constants/app-key"
import { modules } from "@/modules/navigation"

/** 项目配置类型 */
export interface LayoutsConfig {
  /** 侧边栏结构样式，与主题配色独立 */
  sidebarStyle: SidebarStyle
  /** 是否显示设置按钮和面板 */
  showSettings: boolean
  /** 布局模式 */
  layoutMode: LayoutModeEnum
  /** 是否显示标签栏 */
  showTagsView: boolean
  /** 是否显示 Logo */
  showLogo: boolean
  /** 是否固定 Header */
  fixedHeader: boolean
  /** 是否显示页脚 */
  showFooter: boolean
  /** 是否显示消息通知 */
  showNotify: boolean
  /** 是否显示切换主题按钮 */
  showThemeSwitch: boolean
  /** 是否显示全屏按钮 */
  showScreenfull: boolean
  /** 是否显示搜索按钮 */
  showSearchMenu: boolean
  /** 是否缓存标签栏 */
  cacheTagsView: boolean
  /** 开启系统水印 */
  showWatermark: boolean
  /** 是否显示灰色模式 */
  showGreyMode: boolean
  /** 是否显示色弱模式 */
  showColorWeakness: boolean
}

/** 默认配置 */
export const layoutsConfig: LayoutsConfig = {
  sidebarStyle: "rounded",
  layoutMode: LayoutModeEnum.Left,
  showSettings: true,
  showTagsView: true,
  fixedHeader: true,
  showFooter: true,
  showLogo: true,
  showNotify: true,
  showThemeSwitch: true,
  showScreenfull: true,
  showSearchMenu: true,
  cacheTagsView: false,
  showWatermark: false,
  showGreyMode: false,
  showColorWeakness: false
}

/** 各模块独立组合布局；实际共用的配置选项可以覆盖默认值。 */
export function getModuleLayoutsConfig(module: string): LayoutsConfig {
  return { ...layoutsConfig, ...modules[module]?.layout }
}
