"""One JSON boundary for Campfire's command-line adapters."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import typer
from pydantic import BaseModel
from typer.core import TyperGroup, _click

from campfire_cli.common.exceptions import AppError


def emit(value: BaseModel | dict[str, Any], *, err: bool = False) -> None:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=None if err else 2), err=err)


def command_tree(command: Any, name: str) -> dict[str, Any]:
    return {
        "name": name,
        "commands": [
            command_tree(child, child_name)
            for child_name, child in getattr(command, "commands", {}).items()
            if not child.hidden
        ],
    }


def parameter_help(parameter: Any, ctx: Any) -> dict[str, Any]:
    default = parameter.default
    value = {
        "name": parameter.name,
        "kind": parameter.param_type_name,
        "options": [*parameter.opts, *getattr(parameter, "secondary_opts", [])],
        "type": parameter.type.name,
        "required": parameter.required,
        "default": None if callable(default) else parameter.get_default(ctx),
        "multiple": getattr(parameter, "multiple", False),
        "nargs": parameter.nargs,
        "description": getattr(parameter, "help", None),
    }
    if hasattr(parameter.type, "choices"):
        value["choices"] = list(parameter.type.choices)
    return value


class JsonContext(_click.Context):
    """Expose command help as data without invoking command callbacks."""

    def get_help(self) -> str:
        names = []
        context = self
        while context.parent is not None:
            names.append(context.info_name)
            context = context.parent
        payload = {
            "status": "ok",
            "command": ["campfire", *reversed(names)],
            "description": self.command.help,
            "parameters": [
                parameter_help(p, self)
                for p in self.command.get_params(self)
                if not getattr(p, "hidden", False)
            ],
            "commands": [
                {"name": name, "description": child.help}
                for name, child in getattr(self.command, "commands", {}).items()
                if not child.hidden
            ],
        }
        if self.parent is not None:
            payload["global_parameters"] = [
                parameter_help(p, context)
                for p in context.command.get_params(context)
                if not getattr(p, "hidden", False)
            ]
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def configure_json_context(command: Any) -> None:
    command.context_class = JsonContext
    if hasattr(command, "commands") and not command.invoke_without_command:
        command.no_args_is_help = True
    for child in getattr(command, "commands", {}).values():
        configure_json_context(child)


def invoke[ResultT](operation: Callable[[], ResultT]) -> ResultT:
    try:
        return operation()
    except AppError as exc:
        emit(exc.payload(), err=True)
        raise typer.Exit(exc.exit_code) from exc


def usage_payload(exc: _click.UsageError) -> dict[str, object]:
    code = "invalid-command"
    details: dict[str, object] = {}
    if isinstance(exc, _click.exceptions.NoSuchOption):
        code = "invalid-option"
        details["option"] = exc.option_name
    elif isinstance(exc, _click.exceptions.MissingParameter):
        code = "missing-argument"
        if exc.param is not None:
            details["parameter"] = exc.param.name
    elif isinstance(exc, _click.exceptions.BadParameter):
        code = "invalid-argument"
        if exc.param is not None:
            details["parameter"] = exc.param.name
    return {"status": "error", "code": code, "message": exc.format_message(), **details}


class JsonTyperGroup(TyperGroup):
    """Render Typer usage failures with the same machine-readable envelope."""

    def main(self, *args: Any, standalone_mode: bool = True, **kwargs: Any) -> Any:
        configure_json_context(self)
        try:
            result = super().main(*args, standalone_mode=False, **kwargs)
        except _click.exceptions.UsageError as exc:
            if exc.__class__.__name__ == "NoArgsIsHelpError":
                if exc.ctx is not None:
                    typer.echo(exc.ctx.get_help())
                return 0
            emit(usage_payload(exc), err=True)
            self._exit(exc.exit_code, standalone_mode)
        except (KeyboardInterrupt, typer.Abort):
            emit({"status": "error", "code": "cancelled", "message": "操作已取消"}, err=True)
            self._exit(130, standalone_mode)
        except AppError as exc:
            emit(exc.payload(), err=True)
            self._exit(exc.exit_code, standalone_mode)
        except typer.Exit:
            raise
        except Exception as exc:
            emit({"status": "error", "code": "internal-error", "message": str(exc)}, err=True)
            self._exit(1, standalone_mode)
        if standalone_mode and isinstance(result, int) and result:
            self._exit(result, standalone_mode)
        return result

    @staticmethod
    def _exit(code: int, standalone_mode: bool) -> None:
        if standalone_mode:
            raise SystemExit(code)
        raise typer.Exit(code)
