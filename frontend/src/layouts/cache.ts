import type { LayoutsConfig } from "./config"
import type { TagView } from "@/pinia/stores/tags-view"
import { CacheKey } from "@@/constants/cache-key"

// #region 系统布局配置
function scopedKey(key: string, module: string): string {
  return `${key}:${module}`
}

export function getLayoutsConfig(module = "admin") {
  const json = localStorage.getItem(scopedKey(CacheKey.CONFIG_LAYOUT, module))
  return json ? (JSON.parse(json) as LayoutsConfig) : null
}

export function setLayoutsConfig(settings: LayoutsConfig, module = "admin") {
  localStorage.setItem(scopedKey(CacheKey.CONFIG_LAYOUT, module), JSON.stringify(settings))
}

export function removeLayoutsConfig(module = "admin") {
  localStorage.removeItem(scopedKey(CacheKey.CONFIG_LAYOUT, module))
}
// #endregion

// #region 标签栏
export function getVisitedViews(module = "admin") {
  const json = localStorage.getItem(scopedKey(CacheKey.VISITED_VIEWS, module))
  return JSON.parse(json ?? "[]") as TagView[]
}

export function setVisitedViews(views: TagView[], module = "admin") {
  localStorage.setItem(scopedKey(CacheKey.VISITED_VIEWS, module), JSON.stringify(views.map(({ matched: _matched, redirectedFrom: _redirectedFrom, ...view }) => view)))
}

export function getCachedViews(module = "admin") {
  const json = localStorage.getItem(scopedKey(CacheKey.CACHED_VIEWS, module))
  return JSON.parse(json ?? "[]") as string[]
}

export function setCachedViews(views: string[], module = "admin") {
  localStorage.setItem(scopedKey(CacheKey.CACHED_VIEWS, module), JSON.stringify(views))
}
// #endregion
