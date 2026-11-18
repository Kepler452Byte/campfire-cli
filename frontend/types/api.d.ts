/** 所有 api 接口的响应数据都应该准守该格式：信封只表示成功响应，业务失败走 HTTP 4xx/5xx */
interface ApiResponseData<T> {
  code: 0
  data: T
  message: string
}
