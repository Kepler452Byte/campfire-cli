import { usePagination } from "@@/composables/usePagination"

interface ListPage<T> {
  list: T[]
  total: number
  pages: number
}

export function useList<T>(fetcher: (page: number, size: number) => Promise<ListPage<T>>) {
  const { paginationData: pager } = usePagination()
  const rows = ref<T[]>([])
  const loading = ref(false)
  const failed = ref(false)
  let sequence = 0
  async function load(): Promise<void> {
    const seq = ++sequence
    loading.value = true
    failed.value = false
    try {
      const result = await fetcher(pager.currentPage, pager.pageSize)
      if (seq !== sequence) return
      pager.total = result.total
      rows.value = result.list
      const last = Math.max(1, result.pages)
      if (pager.currentPage > last) {
        pager.currentPage = last
        await load()
      }
    } catch {
      // 请求层统一提示错误；列表清除旧结果，避免把失败误认为空数据或最新结果。
      if (seq === sequence) {
        rows.value = []
        pager.total = 0
        failed.value = true
      }
    } finally {
      if (seq === sequence) loading.value = false
    }
  }
  function search() {
    pager.currentPage = 1
    return load()
  }
  function changePage(page: number) {
    pager.currentPage = page
    return load()
  }
  function changeSize(size: number) {
    pager.pageSize = size
    return search()
  }
  onMounted(load)
  onScopeDispose(() => {
    sequence++
  })
  return { pager, rows, loading, failed, load, search, changePage, changeSize }
}
