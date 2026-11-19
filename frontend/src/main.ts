import { Clock, Folder } from "@element-plus/icons-vue"
import { createApp } from "vue"
import SvgIcon from "~virtual/svg-component"
import App from "@/App.vue"
import { initialTicket } from "@/http/session"
import { pinia } from "@/pinia"
import { router } from "@/router"
import "normalize.css"
import "element-plus/theme-chalk/dark/css-vars.css"
import "@@/assets/styles/index.scss"
import "@@/assets/styles/admin-list.scss"
import "@@/assets/styles/three-line-table.scss"
import "virtual:uno.css"

const app = createApp(App, { ticket: initialTicket })
app.component("Clock", Clock)
app.component("Folder", Folder)
app.component("SvgIcon", SvgIcon)
app.use(pinia)
app.use(router)

app.mount("#app")
