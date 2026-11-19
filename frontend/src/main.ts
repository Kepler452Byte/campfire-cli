import { Clock, Folder } from "@element-plus/icons-vue"
import { createApp } from "vue"
import SvgIcon from "~virtual/svg-component"
import App from "@/App.vue"
import { establishSession } from "@/http/session"
import { pinia } from "@/pinia"
import { router } from "@/router"
import "normalize.css"
import "element-plus/theme-chalk/dark/css-vars.css"
import "@@/assets/styles/index.scss"
import "@@/assets/styles/admin-list.scss"
import "@@/assets/styles/three-line-table.scss"
import "virtual:uno.css"

const app = createApp(App)
app.component("Clock", Clock)
app.component("Folder", Folder)
app.component("SvgIcon", SvgIcon)
app.use(pinia)
app.use(router)

establishSession().then(() => router.isReady()).then(() => app.mount("#app")).catch(() => {
  const root = document.getElementById("app")
  if (root) root.textContent = "连接未建立，请使用 campfire web 输出的当前连接链接重新打开。"
})
