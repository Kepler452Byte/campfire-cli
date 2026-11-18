import config from "./config.json"

export interface ModuleConfig {
  enabled: boolean
  title: string
  home: string
  layout: Record<string, unknown>
}
export const modules: Record<string, ModuleConfig> = config
export const enabledModules = Object.entries(modules).filter(([, module]) => module.enabled)

/** 模块路径须精确匹配，不能把 /application 当作 /app。 */
export function getModuleId(path: string): string | undefined {
  const pathname = path.split(/[?#]/)[0]
  return enabledModules.find(([id]) => pathname === `/${id}` || pathname?.startsWith(`/${id}/`))?.[0]
}
export function getRootTarget(): string {
  return enabledModules[0]?.[1].home ?? "/"
}
