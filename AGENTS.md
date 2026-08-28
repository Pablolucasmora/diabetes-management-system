# Instrucciones del proyecto DayBetes

## Convenciones obligatorias

- La carpeta `conventions/` contiene las convenciones, estándares y decisiones de arquitectura del proyecto.
- Antes de analizar, modificar, crear o eliminar código, el agente debe consultar siempre las convenciones aplicables de `conventions/`.
- Las convenciones de `conventions/` deben aplicarse tanto al código nuevo como a las refactorizaciones y correcciones del código existente.
- Si una convención del proyecto contradice una práctica general, prevalece la convención documentada del proyecto.
- Si una convención existente es ambigua, incompleta o contradictoria, el agente debe señalarlo antes de realizar cambios que dependan de esa decisión.

## Convenciones faltantes

- Si el agente detecta que no existe una convención para una decisión nueva que sea necesaria para el trabajo, debe detener la implementación de esa parte y comunicar la carencia al usuario.
- El agente debe explicar qué decisión falta, por qué afecta al diseño y qué alternativas razonables existen.
- El agente debe acordar con el usuario la nueva convención antes de proceder con cambios, ediciones, escrituras o refactorizaciones que dependan de ella.
- Una vez aprobada, la nueva convención debe documentarse en el archivo adecuado dentro de `conventions/` antes o junto con la implementación.
- No se debe inventar una convención local dentro de un módulo, endpoint, tabla o función para evitar consultar esta decisión.
