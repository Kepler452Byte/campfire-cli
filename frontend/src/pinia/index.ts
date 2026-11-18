import piniaPluginPersistedstate from "pinia-plugin-persistedstate"

export const pinia = createPinia()

// 使用持久化插件
pinia.use(piniaPluginPersistedstate)
