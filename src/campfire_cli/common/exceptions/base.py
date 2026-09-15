"""Protocol-neutral application exceptions."""


class AppError(Exception):
    """Base error translated by delivery adapters."""

    exit_code = 1

    def __init__(self, message: str, *, code: str | None = None, **details: object) -> None:
        super().__init__(message)
        self.code = code
        self.details = details

    def payload(self) -> dict[str, object]:
        result: dict[str, object] = {"status": "error", "message": str(self)}
        if self.code is not None:
            result["code"] = self.code
        result.update(self.details)
        return result


class ConfigurationError(AppError):
    """Raised when a Vault cannot be located or configured."""

    exit_code = 2


class GovernanceBlockedError(AppError):
    """Raised when a write is blocked by governance safety rules."""

    exit_code = 3
