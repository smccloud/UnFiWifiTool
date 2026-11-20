from __future__ import annotations


class UniFiError(Exception):
    """Base error for controller communication."""


class UniFiUnavailable(UniFiError):
    """The controller could not be reached."""


class UniFiAuthError(UniFiError):
    """Credentials were rejected or a session could not be established."""


class TwoFactorRequired(UniFiAuthError):
    """The local account requires an interactive 2FA token."""


class UniFiRateLimited(UniFiError):
    """The controller asked us to slow down."""


class UniFiCapabilityError(UniFiError):
    """The requested operation is not supported by the current configuration."""


class UniFiAPIError(UniFiError):
    def __init__(self, message: str, status_code: int | None = None, payload: object | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload
