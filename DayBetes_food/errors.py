class AppError(Exception):
    code = "application_error"
    status_code = 500
    public_message = "Ha ocurrido un error inesperado."
    log_level = "error"

    def __init__(self, internal_message=None, *, fields=None, context=None):
        super().__init__(internal_message or self.public_message)
        self.fields = fields or {}
        self.context = context or {}


class MalformedRequestError(AppError):
    code = "malformed_request"
    status_code = 400
    public_message = "La petición no tiene un formato válido."
    log_level = "info"


class ValidationError(AppError):
    code = "validation_error"
    status_code = 422
    public_message = "Los datos enviados no son válidos."
    log_level = "info"


class AuthenticationError(AppError):
    code = "authentication_required"
    status_code = 401
    public_message = "Necesitas iniciar sesión."
    log_level = "info"


class AuthorizationError(AppError):
    code = "forbidden"
    status_code = 403
    public_message = "No tienes permiso para realizar esta operación."
    log_level = "info"


class NotFoundError(AppError):
    code = "not_found"
    status_code = 404
    public_message = "El recurso no existe o no está disponible."
    log_level = "info"


class ConflictError(AppError):
    code = "conflict"
    status_code = 409
    public_message = "La operación entra en conflicto con el estado actual."
    log_level = "info"


class RateLimitError(AppError):
    code = "rate_limited"
    status_code = 429
    public_message = "Se han realizado demasiadas peticiones. Inténtalo más tarde."
    log_level = "warning"


class ExternalServiceError(AppError):
    code = "external_service_error"
    status_code = 502
    public_message = "El servicio externo no está disponible."
    log_level = "error"


class InfrastructureError(AppError):
    code = "infrastructure_error"
    status_code = 500
    public_message = "No se ha podido completar la operación."
    log_level = "error"
