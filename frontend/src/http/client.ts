import axios from "axios"

export const client = axios.create({ baseURL: "/api/v1", timeout: 30000, headers: { "X-Campfire-Request": "1" } })
