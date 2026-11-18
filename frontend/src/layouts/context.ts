import type { InjectionKey } from "vue"
import { hasInjectionContext, inject, provide } from "vue"

const layoutKey: InjectionKey<string> = Symbol("layout-instance")

/** Each mounted layout owns its state; embedded layouts can supply a unique ID. */
export function provideLayout(id: string): void {
  provide(layoutKey, id)
}

export function useLayoutId(): string {
  return hasInjectionContext() ? inject(layoutKey, "auth") : "auth"
}

export function getLayoutModule(id: string): string {
  return id.split(":")[0]!
}
