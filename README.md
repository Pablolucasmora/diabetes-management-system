# DayBetes — Sistema de gestión personalizada para la diabetes

> Registro preciso de comidas, insulina y contexto diario, como base para entender **cómo responde la glucosa de una persona concreta** y, a futuro, darle recomendaciones hechas a su medida.

| | |
|---|---|
| **Estado** | En producción, uso personal diario (un único usuario) |
| **Web** | [daybetes.com](https://daybetes.com), de acceso privado |
| **Fase** | Trabajo de Fin de Grado (TFG): registro y análisis personal |
| **Stack** | Python · FastHTML · HTMX · PostgreSQL 17 · Tailwind CSS · Docker |
| **Despliegue** | VPS + Cloudflare Tunnel, con despliegue continuo desde GitHub Actions |

---

## Índice

1. [Qué es DayBetes](#1-qué-es-daybetes)
2. [Objetivo y visión](#2-objetivo-y-visión)
3. [Estado actual](#3-estado-actual)
4. [Funcionalidades](#4-funcionalidades)
5. [Modelo de datos](#5-modelo-de-datos)
6. [Arquitectura técnica](#6-arquitectura-técnica)
7. [Despliegue y operación](#7-despliegue-y-operación)
8. [Cómo se desarrolla](#8-cómo-se-desarrolla)
9. [Desarrollo local](#9-desarrollo-local)
10. [Hoja de ruta](#10-hoja-de-ruta)
11. [Documentación del proyecto](#11-documentación-del-proyecto)

---

## 1. Qué es DayBetes

DayBetes nace de una necesidad personal de su autor: **entender cómo reaccionan sus niveles de glucosa** ante lo que come, la insulina que se pone y el resto de factores del día a día. Las aplicaciones comerciales para la diabetes registran datos, pero rara vez aprenden de la persona que las usa. Tratan a todos los usuarios con las mismas reglas, aunque la respuesta glucémica a una misma comida varía mucho de una persona a otra.

DayBetes parte de la idea contraria: **cada persona necesita su propio modelo**. Para construirlo, lo primero es tener datos fiables. Por eso el núcleo actual del proyecto es un sistema de registro muy preciso, que guarda qué se ha comido y además **con qué fiabilidad se conoce cada dato**:
- si el alimento se pesó o se estimó;
- si los macronutrientes son exactos o aproximados;
- si se pesó en crudo o cocinado;
- cuánto se sirvió y cuánto se comió de verdad.

Sobre esos datos se construirán después el análisis de la respuesta glucémica y, en una fase posterior, un algoritmo personalizado que aprenda de los patrones de cada usuario.

---

## 2. Objetivo y visión

El proyecto se plantea en dos fases.

### Fase 1: TFG, estudio personalizado de un individuo (actual)

El Trabajo de Fin de Grado se centra en **una sola persona, el autor**, y tiene tres objetivos:

1. **Construir un sistema de registro de calidad**: comidas con sus porciones, macronutrientes, momento de cada plato, dosis de insulina, zona de inyección y tipo de comida. Cada dato lleva su nivel de confianza y su incertidumbre.
2. **Unir esos registros con los datos de glucosa** del sensor continuo, importándolos de LibreView.
3. **Analizar la respuesta glucémica personal**: qué alimentos, combinaciones, horarios y dosis producen qué curvas de glucosa, con estadísticas de tiempo en rango, comparativas entre días y franjas horarias, y correlaciones entre lo registrado y lo medido.

El resultado esperado del TFG es tanto la herramienta, ya en uso diario, como el análisis de los datos recogidos con ella. El análisis incluye una valoración crítica de qué factores explican la variabilidad de la glucosa en este caso concreto.

### Fase 2: aplicación para personas con diabetes (posterior al TFG)

La ambición a largo plazo es convertir DayBetes en un **acompañante digital para personas con diabetes**, basado en un **algoritmo personalizado por usuario**:

- **Un modelo por persona**, entrenado con sus propios datos de comidas, insulina, glucosa, actividad física, sueño y estrés. No hay un modelo único para todos.
- **Predicción de la respuesta glucémica** ante una comida planificada, antes de comerla.
- **Recomendaciones**: momento de la comida y de la insulina, y avisos de riesgo de hipoglucemia o hiperglucemia, cada vez más precisos a medida que el modelo aprende del usuario.
- **Integración con más fuentes de datos**: Apple Health (frecuencia cardiaca, variabilidad de la frecuencia cardiaca como indicador de estrés, ejercicio, sueño).
- **Varios usuarios**, cada uno con sus datos aislados y su propio modelo.

> DayBetes no es un producto sanitario. Sus análisis y sus futuras recomendaciones son una herramienta de apoyo y no sustituyen el criterio del equipo médico.

---

## 3. Estado actual

La aplicación está **en producción y se usa a diario**. La parte de registro está prácticamente completa. La integración de datos de glucosa y el análisis son lo siguiente.

| Área | Estado |
|---|---|
| Catálogo de alimentos, recetas e ingestas manuales | ✅ Implementado |
| Eventos de comida: planificar, ajustar platos y porciones, confirmar lo comido | ✅ Implementado |
| Confianza e incertidumbre de los macronutrientes | ✅ Implementado |
| Registro de inyecciones de insulina, con zona de inyección | ✅ Implementado |
| Escáner de código de barras + Open Food Facts | ✅ Implementado |
| Comidas de rescate (hipoglucemia) | ✅ Implementado |
| Ajustes: horario de tipos de comida, etiquetas, inyecciones | ✅ Implementado |
| Estadísticas básicas: totales diarios y desglose por tipo de comida | ✅ Implementado |
| Autenticación y sesiones; registro cerrado en producción | ✅ Implementado |
| Despliegue en VPS, CI/CD, copias de seguridad cifradas | ✅ En marcha |
| Nevera (tuppers y sobras reutilizables) | 🟡 Modelo de datos creado, falta la interfaz |
| Importación de glucosa desde LibreView | ⏳ Pendiente (siguiente paso del TFG) |
| Análisis de la respuesta glucémica | ⏳ Pendiente (TFG) |
| Apple Health | ⏳ Pendiente (fase 2) |
| Modelo predictivo y recomendaciones | ⏳ Pendiente (fase 2) |

En cifras: unas 22 000 líneas de Python y 2 000 de JavaScript; 16 tablas; 84 rutas; seis documentos de convenciones; y más de 60 decisiones de arquitectura registradas.

---

## 4. Funcionalidades

La interfaz se organiza en cuatro secciones, a las que se accede desde una barra de navegación flotante (**Menu, Stats, Food, Settings**). Además hay un **carrito** siempre accesible con las comidas en curso.

### 4.1 Alimentos (Food)

- **Biblioteca unificada** de tres tipos de entrada:
  - **alimentos del catálogo**, con valores nutricionales por 100 g;
  - **recetas**, que combinan ingredientes y calculan sus macros;
  - **ingestas manuales**, para comidas de fuera o sin información exacta.
- **Búsqueda en tiempo real** (HTMX), filtros, favoritos y etiquetas.
- **Creación rápida con "smart macros"**: se escribe `120kcal 30hc 12az 20prot` y el sistema rellena los campos. Usa una gramática estricta, que rechaza lo que no entiende en lugar de adivinar. El navegador muestra una vista previa, pero quien decide es siempre el servidor.
- **Escáner de código de barras**: busca el producto en **Open Food Facts** y rellena el formulario de alta, conservando de qué fuente procede cada dato.
- **Biblioteca personal y publicada**: un alimento es privado de quien lo crea hasta que se publica.
- **Comidas de rescate**: un registro rápido de lo que se toma para tratar una hipoglucemia, con sus propias opciones y su propio tipo de comida.

### 4.2 Carrito y eventos de comida

Cada comida es un **evento de ingesta**: se **planifica**, se ajusta y se **confirma como consumida**. Un evento se puede archivar y restaurar. Dentro de un evento:
- **Platos (tandas)**: una comida puede tener varios platos, servidos en momentos distintos. Cada plato tiene su desfase en minutos respecto al inicio de la comida.
- **Porciones**: cada alimento del plato lleva su cantidad, su propio desfase y tres indicadores de calidad: si se pesó de forma estricta, si se pesó en crudo o cocinado, y si sus macros son exactos o aproximados.
- **Datos del evento**: tipo de comida (asignado automáticamente según el horario configurado), hora, si se comió fuera, dosis de insulina, zona de inyección y notas.
- **Confirmación**: al confirmar, se registra lo que se comió de verdad y se calculan la **confianza** y la **incertidumbre** de cada nutriente.

### 4.3 Confianza e incertidumbre

Es una de las piezas diferenciales del proyecto. Para cada evento se calculan:
- la **confianza en la cantidad** (`amount_confidence`): cuánto se sabe de lo que se comió realmente;
- la **confianza en la calidad** (`quality_confidence`): cuánto se sabe de la composición de lo comido;
- la **incertidumbre de cada nutriente** (hidratos, azúcares, grasas, saturadas, proteínas, fibra), entre 0 y 1, ponderada por la cantidad de cada ingrediente y por si su dato es conocido o estimado.

Así, el análisis posterior puede **distinguir un dato fiable de uno aproximado**, en lugar de tratarlos igual. Las reglas exactas están en [`measurement_conventions.md`](conventions/measurement_conventions.md) §6.

### 4.4 Insulina, ajustes y estadísticas

- **Registro de inyecciones de insulina**: rápida o basal, con dosis, momento y zona del cuerpo, en un registro editable.
- **Ajustes**: el horario que asigna automáticamente el tipo de comida (desayuno, almuerzo, comida, merienda, cena...), las etiquetas y las inyecciones.
- **Estadísticas**: totales y promedios diarios de macronutrientes, y desglose por tipo de comida. Es la base sobre la que se construirá el análisis con datos de glucosa.

---

## 5. Modelo de datos

PostgreSQL 17, con **16 tablas**. Las restricciones de integridad, los valores de los enumerados y la propiedad de cada fila se garantizan **también en SQL**, no solo en la aplicación.

| Grupo | Tablas | Para qué |
|---|---|---|
| Usuarios y seguridad | `users`, `auth_sessions`, `auth_rate_limits` | Cuentas, sesiones revocables y límite de intentos de login |
| Alimentos | `catalog`, `food_brands`, `recipe`, `manual_intake` | Alimentos con su información nutricional, marcas, recetas e ingestas manuales |
| Comidas | `intake_event`, `intake_plate`, `portion_detail` | Eventos de comida, sus platos y las porciones de cada uno |
| Insulina y horario | `insulin_injections`, `meal_type_schedule` | Inyecciones y franjas horarias de cada tipo de comida |
| Organización | `tags`, `linked_tags`, `user_favorites` | Etiquetas y favoritos |
| Sobras | `fridge` | Tuppers reutilizables (pendiente de interfaz) |

`portion_detail` usa un **patrón de arco**: cada porción tiene **un único origen** (un alimento del catálogo, una ingesta manual o una receta) y **un único destino** (un plato de un evento, una receta o un tupper de la nevera). Así, una misma tabla describe tanto lo que se come como de qué está hecha una receta.

---

## 6. Arquitectura técnica

### 6.1 Stack

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.12 |
| Web | [FastHTML](https://fastht.ml) 0.14 sobre Starlette 1.x y Uvicorn |
| Interactividad | HTMX 2, con JavaScript propio y mínimo para detalles concretos (escáner, vista previa de macros, avisos) |
| Estilos | Tailwind CSS. El CSS se compila en desarrollo y se versiona |
| Base de datos | PostgreSQL 17, accedida con `psycopg` 3 (SQL explícito, sin ORM) |
| Seguridad | Argon2 para contraseñas, sesiones en base de datos, CSRF, límite de intentos de login |
| Datos externos | Open Food Facts |
| Contenedores | Docker y Docker Compose |
| Infraestructura | VPS de OVH (Ubuntu 26.04 LTS), Cloudflare (DNS, Tunnel, R2), GitHub Actions |

### 6.2 Estructura del código

```
DayBetes_food/
├── main.py              # Arranque de la app, middleware de seguridad y gestión de errores
├── config.py            # Toda la configuración, cargada y validada al arrancar
├── auth/                # Autenticación, sesiones, contraseñas y CSRF
├── domain/              # Reglas de negocio puras: enumerados, dataclasses, nutrición e incertidumbre
├── database/
│   ├── schema.py        # Definición del esquema
│   ├── db_init.py       # Bootstrap y migraciones del esquema
│   └── queries/         # Un módulo por tabla
├── integrations/        # Adaptadores externos (Open Food Facts)
├── routes/              # Endpoints: auth, food, cart, menu, stats, settings, scanner
├── components/          # Componentes de interfaz (funciones Python que devuelven HTML)
└── static/              # CSS compilado, JavaScript e imágenes
```

### 6.3 Principios de diseño

- **HTML desde el servidor.** Las páginas y fragmentos se generan en Python, y HTMX actualiza solo la parte de la página que cambia. Apenas hay estado en el navegador.
- **Capas con responsabilidades claras.** Las rutas validan la entrada y la autorización. `domain/` contiene la lógica pura, sin base de datos. `database/queries/` contiene el SQL, organizado por tabla. Los componentes solo pintan.
- **Dos identidades de base de datos.** La app trabaja con un rol **sin permisos para modificar el esquema**. El esquema solo lo cambia una identidad de migraciones, que no se usa nunca en tiempo de ejecución.
- **La propiedad de los datos se comprueba en SQL.** Cada consulta filtra por usuario, de modo que un fallo en una ruta no puede exponer datos de otra persona.
- **Errores tipados y uniformes.** Un único formato de error, códigos HTTP con significado y mensajes que no revelan información interna.

---

## 7. Despliegue y operación

La aplicación funciona en producción en **[daybetes.com](https://daybetes.com)** desde octubre de 2026.

### 7.1 Cómo llega una visita

```
Navegador ──HTTPS──▶ Cloudflare ──Tunnel (conexión saliente)──▶ VPS
                                                                  │
                                              ┌─── Docker Compose ┴─────────────┐
                                              │ tunnel ─▶ web (FastHTML) ─▶ db │
                                              └─────────────────────────────────┘
```

- **El servidor no tiene ningún puerto web abierto.** El contenedor `cloudflared` abre una conexión **saliente** hacia Cloudflare, y las visitas entran por ella. La IP del servidor no aparece en el DNS, y el firewall solo deja pasar SSH.
- **Acceso privado.** El registro de usuarios está cerrado en producción, y la autenticación de la app es la primera barrera. Está previsto añadir Cloudflare Access para que solo usuarios autorizados lleguen a la web.

### 7.2 Servidor

- VPS de OVH en la UE, con Ubuntu 26.04 LTS.
- Endurecimiento: acceso SSH solo con clave y sin contraseñas ni root; firewall con todo cerrado salvo SSH; parches de seguridad automáticos con reinicio programado cuando hacen falta; swap de reserva; logs de contenedores limitados.

### 7.3 Despliegue continuo

Producción ejecuta siempre la rama `main`, que está protegida: solo admite cambios mediante Pull Request y con la auditoría de dependencias en verde.

```
rama ─▶ Pull Request ─▶ pip-audit ─▶ merge en main ─▶ GitHub Actions
                                                         │  (SSH con clave dedicada y de un solo uso)
                                                         ▼
                                          VPS: git pull ─▶ migraciones ─▶ build + up ─▶ comprobación de salud
```

- **Las migraciones del esquema** se ejecutan en un contenedor de un solo uso **antes** de sustituir la app. Si fallan, la versión anterior sigue funcionando.
- **El usuario de despliegue no tiene terminal.** Su clave solo puede lanzar el script de despliegue, de modo que si se filtrara solo serviría para desplegar lo que ya está en `main`.
- Las dependencias se auditan con `pip-audit` en cada Pull Request y antes de cada despliegue.

### 7.4 Copias de seguridad

- Cada noche se hace un volcado completo de la base de datos, **cifrado con `age` en el propio servidor**. El servidor solo tiene la clave pública, así que puede cifrar pero no descifrar.
- Las copias se guardan en Cloudflare R2, en la jurisdicción de la UE, durante 90 días, y además localmente durante 7 días.
- Un servicio de monitorización avisa si una copia falla **o si no llega a ejecutarse**.
- La restauración se prueba de principio a fin cada mes. Una copia que nunca se ha restaurado no se da por válida.

Los detalles de toda la infraestructura están en [`infra_conventions.md`](conventions/infra_conventions.md).

---

## 8. Cómo se desarrolla

### 8.1 Desarrollo guiado por convenciones

Todas las decisiones de diseño están escritas en [`conventions/`](conventions/), y el código se escribe **siguiéndolas**:

- Cuando aparece una decisión nueva que no está cubierta, se para el desarrollo hasta acordarla y documentarla.
- Las decisiones relevantes se registran con su contexto, las alternativas consideradas y el motivo de la elección.
- El código y sus comentarios se escriben en inglés. Los textos de la interfaz y la documentación, en español.

### 8.2 Auditorías por tabla

El código se revisa **tabla a tabla** contra las convenciones: esquema, restricciones, consultas, rutas e interfaz que dependen de cada una. Cada auditoría produce una lista de hallazgos y un plan de corrección, que se aplica y se verifica contra la base de datos real. En este proceso se usan agentes de [Claude Code](https://claude.com/claude-code) definidos en [`.claude/agents/`](.claude/agents/): `audit-tabla` para auditar y `propose` para preparar el plan.

### 8.3 Flujo de trabajo

[GitHub Flow](https://docs.github.com/en/get-started/using-github/github-flow): cada cambio en su rama, una Pull Request revisada y la fusión en `main`, que despliega automáticamente. Los commits siguen el formato [Conventional Commits](https://www.conventionalcommits.org) (`feat`, `fix`, `docs`, `chore`...).

---

## 9. Desarrollo local

Requisitos: Docker (o Docker Desktop).

```sh
git clone https://github.com/Pablolucasmora/diabetes-management-system.git
cd diabetes-management-system
cp .env.example .env        # rellenar los valores (no se suben nunca a git)
docker compose up -d        # base de datos, app con recarga automática y Tailwind en modo watch
```

La app queda en `http://localhost:8000`. En desarrollo, el registro de usuarios está abierto y el esquema se crea solo al arrancar.

Desarrollo y producción usan **archivos de Compose separados** (`docker-compose.yml` y `docker-compose.prod.yml`) y **volúmenes de datos distintos**. Los comandos de producción se ejecutan siempre con `./scripts/prod.sh`.

---

## 10. Hoja de ruta

**Corto plazo**
- Cloudflare Access delante de la aplicación.
- Límite de intentos en el registro y respuesta `429` en los bloqueos de login.
- Interfaz de la nevera (sobras y tuppers).

**TFG**
- Importación de datos de glucosa desde **LibreView**: lecturas del sensor, tendencias e insulina.
- Panel de **análisis glucémico**: curvas tras cada comida, tiempo en rango, comparativas por día y franja horaria.
- **Análisis de correlación** entre lo registrado (macros, cantidades, horarios, dosis, confianza de los datos) y la respuesta de glucosa.
- Memoria del TFG con los resultados del análisis personal.

**Después del TFG**
- Integración con **Apple Health**: actividad, sueño, frecuencia cardiaca y su variabilidad.
- **Modelo predictivo personalizado** por usuario y motor de recomendaciones.
- Soporte de varios usuarios y una experiencia pensada para móvil.

---

## 11. Documentación del proyecto

| Documento | Contenido |
|---|---|
| [`code_conventions.md`](conventions/code_conventions.md) | Capas, transacciones, tipado, seguridad, configuración y esquema |
| [`measurement_conventions.md`](conventions/measurement_conventions.md) | Unidades, cantidades, porciones, platos, confianza e incertidumbre |
| [`error_conventions.md`](conventions/error_conventions.md) | Tipos de error, códigos HTTP, mensajes y registros |
| [`frontend_conventions.md`](conventions/frontend_conventions.md) | Componentes, HTMX, interfaz e idioma |
| [`infra_conventions.md`](conventions/infra_conventions.md) | Entornos, despliegue, servidor, copias de seguridad y dependencias |
| [`decisions.md`](conventions/decisions.md) | Registro histórico de decisiones de arquitectura |
