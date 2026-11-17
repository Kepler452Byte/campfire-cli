"""Protocol-neutral application exceptions."""


class AppError(Exception):
    """Base error translated by delivery adapters."""

    exit_code = 1
    error_code = "operation-failed"

    def __init__(self, message: str, *, code: str | None = None, **details: object) -> None:
        super().__init__(message)
        self.code = code
        self.details = details

    def payload(self) -> dict[str, object]:
        result: dict[str, object] = {"status": "error", "message": str(self)}
        result["code"] = self.code or self.error_code
        result.update(self.details)
        return result


class ConfigurationError(AppError):
    """Raised when a Vault cannot be located or configured."""

    exit_code = 2
    error_code = "configuration-error"


class InputError(AppError):
    """Raised when a caller supplied a syntactically invalid command value."""

    exit_code = 2
    error_code = "invalid-input"


class GovernanceBlockedError(AppError):
    """Raised when a write is blocked by governance safety rules."""

    exit_code = 3
    error_code = "governance-blocked"


class JobError(AppError):
    """Expose a stable code for local execution and scheduling failures."""

    def __init__(self, code: str, message: str, **details: object) -> None:
        super().__init__(message, code=code, **details)
        self.blocked = code in {
            "busy",
            "stale-plan",
            "foreign-job",
            "already-deployed",
            "upgrade-active",
            "workspace-binding-changed",
            "environment-missing",
            "recovery-required",
        }
        self.exit_code = 3 if self.blocked else (2 if code.startswith("invalid-") else 1)

    def payload(self) -> dict[str, object]:
        return {**super().payload(), "status": "blocked" if self.blocked else "error"}
