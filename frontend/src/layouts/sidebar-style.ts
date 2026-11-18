/** 侧边栏结构预设；项目默认值在 layouts/config.ts 中选择。 */
export type SidebarStyle = "rounded" | "compact" | "classic"

export const sidebarStyles: { value: SidebarStyle, label: string }[] = [
  { value: "rounded", label: "圆角" },
  { value: "compact", label: "紧凑" },
  { value: "classic", label: "经典" }
]
