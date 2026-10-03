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
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2), err=err)


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
        try:
            result = super().main(*args, standalone_mode=False, **kwargs)
        except _click.exceptions.UsageError as exc:
            if exc.__class__.__name__ == "NoArgsIsHelpError":
                if exc.ctx is not None:
                    typer.echo(exc.ctx.get_help())
                self._exit(exc.exit_code, standalone_mode)
            emit(usage_payload(exc), err=True)
            self._exit(exc.exit_code, standalone_mode)
        if standalone_mode and isinstance(result, int) and result:
            self._exit(result, standalone_mode)
        return result

    @staticmethod
    def _exit(code: int, standalone_mode: bool) -> None:
        if standalone_mode:
            raise SystemExit(code)
        raise typer.Exit(code)
