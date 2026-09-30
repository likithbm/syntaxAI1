from __future__ import annotations


class AppError(Exception):
    """Error that is safe to show to the user."""

    def __init__(self, code: str, message: str, status: int = 400, retryable: bool = False, details=None):
        super().__init__(message)
        self.code, self.message, self.status, self.retryable, self.details = code, message, status, retryable, details

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "retryable": self.retryable,
                          "details": self.details}}
