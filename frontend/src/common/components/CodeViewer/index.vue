<script setup lang="ts">
import { defaultKeymap } from "@codemirror/commands"
import { foldGutter, foldKeymap, HighlightStyle, syntaxHighlighting } from "@codemirror/language"
import { highlightSelectionMatches, searchKeymap } from "@codemirror/search"
import { Compartment, EditorSelection, EditorState } from "@codemirror/state"
import { drawSelection, EditorView, highlightSpecialChars, keymap, lineNumbers } from "@codemirror/view"
import { tags } from "@lezer/highlight"
import { loadLanguage } from "./languages"

const props = defineProps<{ path: string, content: string, active: boolean }>()
const host = ref<HTMLElement>()
const language = new Compartment()
let view: EditorView | undefined
let disposed = false
const highlight = HighlightStyle.define([
  { tag: [tags.keyword, tags.number, tags.bool], color: "var(--theme-code-keyword)" },
  { tag: [tags.string, tags.regexp], color: "var(--theme-code-string)" },
  { tag: tags.comment, color: "var(--theme-code-comment)", fontStyle: "italic" },
  { tag: [tags.function(tags.variableName), tags.typeName], color: "var(--theme-code-definition)" }
])
onMounted(async () => {
  view = new EditorView({
    parent: host.value,
    doc: props.content,
    extensions: [
      EditorState.readOnly.of(true),
      EditorView.editable.of(false),
      EditorView.contentAttributes.of({ "tabindex": "0", "aria-label": `源码 ${props.path}` }),
      lineNumbers(),
      highlightSpecialChars(),
      drawSelection(),
      foldGutter(),
      highlightSelectionMatches(),
      keymap.of([...searchKeymap, ...foldKeymap, ...defaultKeymap]),
      syntaxHighlighting(highlight),
      language.of([]),
      EditorView.theme({
        "&": { height: "100%", color: "var(--el-text-color-primary)", backgroundColor: "var(--el-bg-color)" },
        ".cm-scroller": { overflow: "auto", fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace", fontSize: "13px", lineHeight: "1.7" },
        ".cm-gutters": { backgroundColor: "var(--el-fill-color-light)", color: "var(--el-text-color-secondary)", borderColor: "var(--el-border-color)" },
        ".cm-content": { padding: "12px 0" },
        ".cm-line": { padding: "0 16px" },
        ".cm-panels": { color: "var(--el-text-color-primary)", backgroundColor: "var(--el-fill-color-light)" },
        ".cm-searchMatch": { backgroundColor: "var(--el-color-primary-light-8)" },
        "&.cm-focused .cm-selectionBackground, .cm-selectionBackground, ::selection": { backgroundColor: "var(--el-color-primary-light-7)" }
      })
    ]
  })
  try {
    const extension = await loadLanguage(props.path)
    if (!disposed) view.dispatch({ effects: language.reconfigure(extension) })
  } catch {
    // 语言资源加载失败时保留可读的纯文本。
  }
})
watch(() => props.content, (content) => {
  if (!view || content === view.state.doc.toString()) return
  const selection = view.state.selection.main
  const scroll = view.scrollDOM.scrollTop
  view.dispatch({
    changes: { from: 0, to: view.state.doc.length, insert: content },
    selection: EditorSelection.single(Math.min(selection.anchor, content.length), Math.min(selection.head, content.length))
  })
  view.scrollDOM.scrollTop = scroll
})
watch(() => props.active, async (active) => {
  if (active) {
    await nextTick()
    view?.requestMeasure()
  }
})
onBeforeUnmount(() => {
  disposed = true
  view?.destroy()
})
</script>

<template>
  <div ref="host" class="code-viewer" />
</template>

<style scoped lang="scss">
.code-viewer {
  height: 100%;
  min-height: 0;
  overflow: hidden;
}
</style>
