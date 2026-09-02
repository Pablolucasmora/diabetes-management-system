class AppError(Exception):
    code = "application_error"
    status_code = 500
    public_message = "Ha ocurrido un error inesperado."
    log_level = "error"

    def __init__(self, internal_message=None, *, fields=None, context=None):
        super().__init__(internal_message or self.public_message)
        self.fields = fields or {}
        self.context = context or {}


class ValidationError(AppError):
    code = "validation_error"
    status_code = 422
    public_message = "Los datos enviados no son válidos."
    log_level = "info"


class ConflictError(AppError):
    code = "conflict"
    status_code = 409
    public_message = "La operación entra en conflicto con el estado actual."
    log_level = "info"


class InfrastructureError(AppError):
    code = "infrastructure_error"
    status_code = 500
    public_message = "No se ha podido completar la operación."
    log_level = "error"
