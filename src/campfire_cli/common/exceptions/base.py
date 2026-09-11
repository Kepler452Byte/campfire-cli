"""Protocol-neutral application exceptions."""


class AppError(Exception):
    """Base error translated by delivery adapters."""

    exit_code = 1


class ConfigurationError(AppError):
    """Raised when a Vault cannot be located or configured."""

    exit_code = 2


class GovernanceBlockedError(AppError):
    """Raised when a write is blocked by governance safety rules."""

    exit_code = 3
