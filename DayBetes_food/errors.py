class AppError(Exception):
    code = "application_error"
    status_code = 500
    public_message = "An unexpected error occurred."
    log_level = "error"

    def __init__(self, internal_message=None, *, fields=None, context=None):
        super().__init__(internal_message or self.public_message)
        self.fields = fields or {}
        self.context = context or {}


class MalformedRequestError(AppError):
    code = "malformed_request"
    status_code = 400
    public_message = "The request is not well formed."
    log_level = "info"


class ValidationError(AppError):
    code = "validation_error"
    status_code = 422
    public_message = "The submitted data is not valid."
    log_level = "info"


class AuthenticationError(AppError):
    code = "authentication_required"
    status_code = 401
    public_message = "You need to log in."
    log_level = "info"


class AuthorizationError(AppError):
    code = "forbidden"
    status_code = 403
    public_message = "You are not allowed to perform this action."
    log_level = "info"


class NotFoundError(AppError):
    code = "not_found"
    status_code = 404
    public_message = "The resource does not exist or is not available."
    log_level = "info"


class ConflictError(AppError):
    code = "conflict"
    status_code = 409
    public_message = "The action conflicts with the current state."
    log_level = "info"


class RateLimitError(AppError):
    code = "rate_limited"
    status_code = 429
    public_message = "Too many requests. Please try again later."
    log_level = "warning"


class ExternalServiceError(AppError):
    code = "external_service_error"
    status_code = 502
    public_message = "The external service is not available."
    log_level = "error"


class InfrastructureError(AppError):
    code = "infrastructure_error"
    status_code = 500
    public_message = "The action could not be completed."
    log_level = "error"
