import { request } from "@/http/axios"

export interface ScriptEntry { name: string, path: string, kind: "directory" | "file" }
export interface ScriptFile { path: string, content: string, size: number }
export const getScriptProjects = () => request<{ root: string, projects: string[] }>({ url: "/scripts" })
export const getScriptDirectory = (project: string, path = "") => request<{ entries: ScriptEntry[] }>({ url: `/scripts/${encodeURIComponent(project)}/tree`, params: { path } })
export const getScriptFile = (project: string, path: string) => request<ScriptFile>({ url: `/scripts/${encodeURIComponent(project)}/file`, params: { path } })
