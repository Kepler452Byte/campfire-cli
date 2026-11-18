"""Convert supported agent inputs to the runtime argv without persisting a duplicate command."""

from pathlib import Path

from campfire_cli.common.exceptions import JobError


def compile_agent(data: object) -> list[str]:
    if not isinstance(data, dict) or set(data) - {"kind", "executable", "args", "prompt"}:
        raise JobError("invalid-agent", "agent requires kind, executable, prompt; optional args")
    kind, executable, prompt = (data.get(key) for key in ("kind", "executable", "prompt"))
    args = data.get("args", [])
    if (
        not isinstance(kind, str)
        or kind not in {"codex", "claude"}
        or not isinstance(executable, str)
        or not Path(executable).is_absolute()
        or any(char in executable for char in "\0\r\n")
        or not isinstance(prompt, str)
        or not prompt.strip()
        or "\0" in prompt
        or not isinstance(args, list)
        or any(not isinstance(arg, str) or "\0" in arg or arg == "--" for arg in args)
    ):
        raise JobError("invalid-agent", "Use codex/claude, an absolute executable, args and prompt")
    return [executable, "exec" if kind == "codex" else "-p", *args, "--", prompt]
