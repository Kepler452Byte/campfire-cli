import type { Extension } from "@codemirror/state"
import { StreamLanguage } from "@codemirror/language"

export async function loadLanguage(path: string): Promise<Extension> {
  const extension = path.split(".").pop()?.toLowerCase()
  switch (extension) {
    case "py": return (await import("@codemirror/lang-python")).python()
    case "js": case "mjs": case "cjs": case "jsx": return (await import("@codemirror/lang-javascript")).javascript({ jsx: true })
    case "ts": case "tsx": return (await import("@codemirror/lang-javascript")).javascript({ typescript: true, jsx: extension === "tsx" })
    case "json": return (await import("@codemirror/lang-json")).json()
    case "yml": case "yaml": return (await import("@codemirror/lang-yaml")).yaml()
    case "md": return (await import("@codemirror/lang-markdown")).markdown()
    case "html": case "htm": return (await import("@codemirror/lang-html")).html()
    case "css": return (await import("@codemirror/lang-css")).css()
    case "sh": case "bash": case "zsh": return StreamLanguage.define((await import("@codemirror/legacy-modes/mode/shell")).shell)
    case "ps1": return StreamLanguage.define((await import("@codemirror/legacy-modes/mode/powershell")).powerShell)
    default: return []
  }
}
