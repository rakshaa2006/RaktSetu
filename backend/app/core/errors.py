"""Domain errors. Each carries the HTTP status the API layer should return."""


class DomainError(Exception):
    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    status_code = 404


class UnauthorizedError(DomainError):
    status_code = 401


class ForbiddenError(DomainError):
    status_code = 403


class ConflictError(DomainError):
    status_code = 409


class InvalidTransition(DomainError):
    status_code = 409


class RuleViolation(DomainError):
    status_code = 422
