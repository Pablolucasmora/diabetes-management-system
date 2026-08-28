# Convenciones de errores - DayBetes

Este documento define cómo se clasifican, propagan, registran y muestran los errores en DayBetes.

Su objetivo es que un mismo problema tenga siempre:

- la misma categoría interna;
- el mismo código estable;
- el mismo status HTTP;
- el mismo formato de respuesta;
- un mensaje público coherente;
- el mismo tratamiento de logging.

Este documento complementa `conventions/code_conventions.md` y `conventions/measurement_conventions.md`.

## 1. Principios generales

- Un error no se representa indistintamente mediante `None`, `False`, `[]`, texto plano o una excepción genérica.
- Los resultados falsy se reservan para resultados de negocio definidos por el contrato de la función.
- Los errores técnicos no se convierten silenciosamente en resultados exitosos.
- Cada error se clasifica una sola vez y se traduce de forma uniforme en el boundary correspondiente.
- Los códigos internos son estables y no dependen del idioma del mensaje visible.
- Los mensajes públicos no exponen SQL, tracebacks, nombres de tablas, rutas internas, tokens ni datos de otros usuarios.
- El usuario recibe información suficiente para corregir la petición, pero no detalles internos innecesarios.
- Un error inesperado se registra internamente con contexto seguro y se muestra al usuario mediante un mensaje genérico.

## 2. Jerarquía de excepciones

Todas las excepciones de aplicación viven en un módulo central, por ejemplo:

```text
DayBetes_food/domain/errors.py
```

No se crean excepciones equivalentes dentro de rutas, componentes o módulos CRUD.

La jerarquía base es:

```python
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


class MalformedRequestError(AppError):
    code = "malformed_request"
    status_code = 400
    public_message = "La petición no tiene un formato válido."
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
```

Las clases pueden incluir contexto interno y errores por campo, pero esos datos no deben formar parte automáticamente de la respuesta pública.

## 3. Catálogo de errores

### 3.1 `malformed_request`

La petición no puede interpretarse estructuralmente.

Ejemplos:

- formato JSON inválido;
- parámetro de ruta con formato imposible;
- tipo de contenido no soportado;
- parámetro obligatorio ausente cuando impide interpretar la petición.

Respuesta: HTTP `400`.

### 3.2 `validation_error`

La petición se ha interpretado correctamente, pero sus valores no cumplen las reglas.

Ejemplos:

- cantidad negativa;
- enum desconocido;
- fecha inválida;
- booleano no reconocido;
- dosis fuera de rango;
- combinación incompatible de campos.

Respuesta:

- JSON y HTML tradicional: HTTP `422`.
- HTMX cuando el error debe insertarse visualmente en un formulario: HTTP `200` con el fragmento mínimo de error definido en `code_conventions.md:9.5`.

### 3.3 `authentication_required`

La petición requiere una sesión válida y no existe una sesión válida.

Respuesta:

- HTML tradicional: `302` a login cuando el flujo sea de navegación.
- HTMX: `401` y `HX-Redirect` a login.
- JSON: `401` con error estructurado.

### 3.4 `forbidden`

El usuario está autenticado y sabe legítimamente que el recurso o la acción existen, pero no tiene el permiso requerido.

Se utiliza `403` cuando la existencia ya es conocida por el usuario de forma legítima, por ejemplo porque el recurso es público, aparece en una lista que puede consultar o ha sido compartido explícitamente con él. No se utiliza `403` en una consulta directa por un identificador opaco cuando ese código confirmaría que el recurso existe.

Respuesta: HTTP `403`.

### 3.5 `not_found`

El recurso no existe, está archivado y no es visible, o pertenece a otro usuario cuya existencia no debe revelarse.

Respuesta: HTTP `404`.

La respuesta pública debe ser la misma para “no existe” y “existe pero no es visible” cuando ambas situaciones no deban distinguirse.

Regla de decisión:

- `403`: el usuario puede saber que el recurso existe, pero carece de permiso para la operación.
- `404`: no debe confirmarse que el recurso existe, o el recurso no existe realmente.

La capa interna puede conservar la causa real para auditoría segura sin cambiar la respuesta pública.

### 3.6 `conflict`

La petición es válida, pero no puede aplicarse porque entra en conflicto con otro dato o con el estado actual.

Ejemplos:

- constraint de unicidad;
- versión obsoleta;
- transición de estado no permitida;
- operación repetida que el contrato define como conflicto.

Respuesta: HTTP `409`.

### 3.7 `rate_limited`

La petición ha superado el límite definido para la operación.

Respuesta: HTTP `429`. Cuando proceda, incluir `Retry-After`.

La estrategia exacta de rate limiting por operación, identidad y almacenamiento se definirá en la fase de exposición multiusuario o de servicios externos. En la fase personal son obligatorios el código `429`, los límites configurables y la ausencia de mensajes que revelen cuentas existentes; no se debe inventar una política diferente por endpoint.

### 3.8 `external_service_error`

Un servicio externo ha fallado, ha agotado su timeout o ha devuelto una respuesta inválida.

Respuesta: HTTP `502` o `503` según si el fallo pertenece a un upstream concreto o a una indisponibilidad temporal conocida.

El usuario no recibe el nombre técnico del proveedor ni el detalle de la excepción.

### 3.9 `infrastructure_error`

Se ha producido un fallo interno de base de datos, conexión, configuración en ejecución o infraestructura que no pertenece a la entrada del usuario.

Respuesta: HTTP `500`.

El error se devuelve mediante un mensaje genérico. El registro con traceback se realiza una sola vez según la política de la sección 10.3.

## 4. Contexto interno del error

Un `AppError` puede transportar información interna estructurada:

```python
raise ValidationError(
    "Invalid amount",
    fields={"amount_g": "Must be greater than zero."},
)
```

El contexto interno puede incluir:

- operación;
- entidad;
- identificador técnico;
- usuario autenticado;
- código de constraint;
- versión esperada y actual;
- excepción original como `__cause__`.

Cuando una capa envuelve una excepción, debe conservar la cadena causal con la sintaxis nativa de Python:

```python
try:
    repository_operation()
except DatabaseError as exc:
    raise InfrastructureError("Could not persist event") from exc
```

No se asigna manualmente `error.__cause__` ni se reemplaza la excepción original sin `from`.

Nunca debe incluir:

- contraseñas;
- tokens o cookies;
- hashes sensibles;
- secretos de configuración;
- datos médicos detallados innecesarios;
- filas completas de otros usuarios;
- SQL con valores sensibles.

## 5. Errores de validación por campo

Cuando el error afecta a campos concretos, se utiliza un mapa estable:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Los datos enviados no son válidos.",
    "fields": {
      "amount_g": "Debe ser mayor que cero.",
      "insulin_type": "Tipo de insulina no válido."
    }
  }
}
```

Reglas:

- El nombre de cada campo coincide con el nombre del contrato de entrada.
- No se utilizan nombres internos de columnas si el formulario usa otro contrato, salvo que sean iguales por diseño.
- Un campo puede tener un único mensaje principal y una lista de códigos si se necesita más detalle.
- Los mensajes técnicos no se envían al cliente.
- El orden de los errores debe ser estable para facilitar la interfaz y los tests.
- Los errores globales se representan con una clave como `"_form"` o mediante el mensaje general definido por el componente.

## 6. Formato JSON

Todas las respuestas JSON de error utilizan esta estructura:

```json
{
  "error": {
    "code": "not_found",
    "message": "El recurso no existe o no está disponible.",
    "fields": {}
  }
}
```

Además, el boundary añade un `request_id` de correlación:

```json
{
  "error": {
    "code": "infrastructure_error",
    "message": "No se ha podido completar la operación.",
    "fields": {}
  },
  "request_id": "01J..."
}
```

Reglas:

- `code` es obligatorio y estable.
- `message` es seguro para mostrar al usuario.
- `fields` es un objeto; si no aplica, se devuelve `{}`.
- No devolver una excepción serializada directamente.
- No usar respuestas incompatibles como `{"detail": ...}` para endpoints que sigan este contrato.
- Los endpoints JSON deben usar `application/json` también cuando responden con error.
- `request_id` debe aparecer en la respuesta y en el log correspondiente.
- El cliente puede proporcionar un identificador de correlación válido, pero el servidor debe generar uno si falta y no debe confiar en valores manipulados para seguridad.

## 7. Formato HTML y HTMX

Las respuestas HTML de error utilizan el componente visual común de errores.

El componente debe:

- mostrar un título común;
- mostrar el mensaje público;
- poder mostrar errores por campo cuando el formulario lo requiera;
- mantener una estructura HTML compatible con el target HTMX;
- no imprimir detalles técnicos.

Reglas HTMX:

- Los errores de validación apuntan a un target visible y estable.
- Los errores de validación visual HTMX utilizan HTTP `200` y el fragmento mínimo definido en `code_conventions.md:9.5`.
- Los errores HTMX que no sean validación visual conservan el status semántico de su categoría.
- Un `HX-Trigger` de error solo se envía si el evento está documentado.
- Una respuesta de navegación utiliza `HX-Redirect`, no un fragmento de error ambiguo.
- No devolver un cuerpo vacío para un error que el usuario necesita ver.
- Las respuestas de error incluyen el header `X-Request-ID` con el mismo identificador usado en el log.

## 8. Traducción por capa

### 8.1 CRUD

El CRUD:

- devuelve el resultado definido por su contrato;
- lanza `NotFoundError` cuando debe distinguir una entidad inexistente;
- lanza `ConflictError` ante unicidad, versión o estado incompatible;
- propaga excepciones SQL e infraestructura;
- no crea respuestas HTTP;
- no traduce errores a HTML o JSON.

### 8.2 Servicios

El servicio:

- aplica reglas de negocio;
- puede transformar una excepción técnica en `InfrastructureError` si añade contexto;
- no oculta la causa original, que debe conservarse mediante `raise NuevaExcepcion(...) from exc`;
- coordina rollback mediante la transacción definida en `code_conventions.md`;
- no depende del transporte HTTP.

### 8.3 Endpoints

El endpoint:

- convierte la entrada HTTP en dataclass;
- llama al servicio o CRUD;
- traduce errores conocidos a la respuesta correspondiente;
- no inventa códigos ni mensajes distintos para el mismo error;
- no captura `Exception` para devolver siempre `400`;
- deja los errores inesperados al handler global cuando exista.

### 8.4 Handler global

Debe existir un boundary común para transformar `AppError` y excepciones inesperadas en:

- respuesta JSON;
- fragmento HTML;
- respuesta HTMX;
- redirect cuando corresponda.

El handler global registra las excepciones inesperadas una sola vez y evita que cada endpoint implemente su propia traducción.

## 9. Autenticación y errores de seguridad

- Login, registro y recuperación de credenciales usan mensajes genéricos.
- No se distingue públicamente entre usuario inexistente y contraseña incorrecta.
- Un fallo CSRF devuelve `403` con mensaje genérico.
- Un recurso ajeno se convierte en `404` cuando su existencia debe ocultarse.
- No se registra el token CSRF, el token de sesión ni su contenido.
- Los errores de autorización no incluyen información sobre el propietario real del recurso.

## 10. Logging de errores

### 10.1 Niveles

- `DEBUG`: información diagnóstica no necesaria en producción.
- `INFO`: validaciones rechazadas, recursos inexistentes y conflictos esperables cuando sean útiles para métricas.
- `INFO` no debe utilizarse para registrar individualmente cada error esperado en endpoints de tráfico elevado; en ese caso se usan métricas agregadas o `DEBUG`.
- `WARNING`: rate limiting, fallos recuperables o degradación de servicios.
- `ERROR`: errores de infraestructura, servicios externos y fallos inesperados.
- `CRITICAL`: fallo que impide arrancar o continuar de forma segura.

### 10.2 Datos mínimos

Un log de error puede incluir:

- `error_code`;
- operación;
- módulo;
- entidad;
- ID técnico;
- `user_id` si es seguro;
- request ID o correlation ID;
- status resultante.

No incluir contraseñas, tokens, cookies, hashes, secretos ni datos médicos completos.

### 10.3 No duplicar logs

La excepción se registra con traceback una sola vez, en el boundary que la convierte en respuesta. Las capas inferiores pueden añadir contexto y propagarla, pero no deben imprimir ni registrar repetidamente la misma excepción. Esta es la regla canónica para todo el documento.

## 11. Errores inesperados

Una excepción no clasificada sigue este flujo:

1. Se revierte la transacción si el contexto es propietario.
2. Se propaga hasta el boundary global.
3. Se registra con traceback y contexto seguro.
4. Se devuelve `infrastructure_error` y HTTP `500`.
5. No se muestra la excepción original al usuario.

No se permite:

```python
try:
    operation()
except Exception:
    return False
```

Tampoco se permite convertir cualquier excepción en HTTP `400`, porque eso clasifica un fallo del servidor como error del cliente.

## 12. Compatibilidad con la primera fase

Durante la fase de recopilación personal, no es obligatorio implementar todos los tipos avanzados de respuesta o localización. Sí son obligatorios:

- catálogo central de errores;
- códigos estables;
- no ocultar errores SQL como resultados falsy;
- mensajes genéricos para autenticación;
- formato común para errores HTML/JSON;
- status HTTP coherente;
- logging sin datos sensibles.

Los handlers avanzados para múltiples transportes, traducciones y métricas detalladas pueden incorporarse progresivamente sin cambiar los códigos internos.

## 13. Tests

Cada error debe probarse en dos niveles:

### 13.1 Tests de dominio y servicios

- excepción correcta;
- código correcto;
- contexto interno correcto;
- rollback cuando corresponda;
- ausencia de filtración de datos.

### 13.2 Tests de endpoints

- status HTTP correcto;
- estructura JSON o HTML correcta;
- mensaje público correcto;
- campos de validación correctos;
- headers HTMX correctos;
- traducción de `NotFoundError` a `404`;
- traducción de `ConflictError` a `409`;
- traducción de errores inesperados a `500`.

## 14. Checklist de auditoría de errores

Para cada función o endpoint se comprobará:

- ¿Qué resultados normales puede devolver?
- ¿Qué error representa “no encontrado”?
- ¿Distingue `False` de `NotFoundError`?
- ¿Qué errores de validación puede producir?
- ¿Qué errores de conflicto puede producir?
- ¿Propaga los errores de infraestructura?
- ¿Quién posee el rollback?
- ¿Qué status HTTP corresponde?
- ¿Existe un mensaje público común?
- ¿La respuesta JSON/HTML/HTMX tiene el formato estándar?
- ¿Se filtra algún detalle sensible?
- ¿Se registra el error una sola vez?
- ¿Hay tests para los caminos de error?

No se considera terminada una operación hasta que su contrato de éxito y sus contratos de error estén documentados y probados.
