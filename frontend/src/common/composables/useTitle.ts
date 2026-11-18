import { APP_TITLE } from "@@/constants/app"

/** 动态标题 */
const dynamicTitle = ref<string>("")

/** 设置标题 */
function setTitle(title?: string) {
  dynamicTitle.value = title ? `${APP_TITLE} | ${title}` : APP_TITLE
}

// 监听标题变化
watch(dynamicTitle, (value, oldValue) => {
  if (document && value !== oldValue) {
    document.title = value
  }
})

/** 标题 Composable */
export function useTitle() {
  return { setTitle }
}
