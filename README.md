# DayBetes — Sistema de Gestión Personalizada para Diabetes

## 1. Introducción y Contexto del Proyecto

Este documento describe el estado actual del proyecto DayBetes, un sistema integral diseñado para el estudio personalizado de la diabetes y el acompañamiento diario en la gestión de esta condición crónica. El proyecto surge de la necesidad personal de su creador de comprender cómo reaccionan los niveles de glucosa ante diversos factores cotidianos, con el objetivo final de construir un modelo de aprendizaje automático que aprenda de los patrones individuales de cada usuario para ofrecer recomendaciones personalizadas.

El alcance del proyecto es ambicioso pero claro: desarrollar una aplicación que funcione como acompañante digital para personas diabéticas, facilitando el registro diario de alimentos, insulina, actividad física y otros factores determinantes en el control glucémico. A diferencia de las soluciones comerciales existentes, este sistema busca personalizarse completamente para cada usuario, aprendiendo de sus datos específicos y adaptándose a sus características individuales.

La arquitectura del proyecto se fundamenta en principios de modularidad y escalabilidad. El sistema está diseñado para funcionar inicialmente como un estudio personalizado de un solo individuo, pero con la capacidad de expandirse para servir a múltiples usuarios simultáneamente. Cada usuario tendrá su propio modelo de aprendizaje que aprenderá de sus patrones únicos, permitiendo recomendaciones cada vez más precisas y útiles.

---

## 2. Estado Actual del Proyecto

### 2.1 Fase de Desarrollo

El proyecto se encuentra actualmente en una **fase intermedia de desarrollo**. La infraestructura base está establecida, incluyendo la base de datos, el framework web y los componentes principales de la interfaz de usuario. Sin embargo, muchas funcionalidades están en desarrollo o pendientes de implementación completa.

El estado actual puede caracterizarse como **MVP (Minimum Viable Product) en construcción**: las piezas fundamentales están en su lugar, pero el sistema aún no está completamente funcional para uso diario. Se han implementado los cimientos sobre los cuales se construirán las funcionalidades completas de registro, análisis y predicción.

### 2.2 Componentes Implementados

La aplicación cuenta con los siguientes componentes funcionales:

- **Sistema de navegación**: Una isla flotante底部 que permite navegar entre las principales secciones de la aplicación (Menu, Stats, Food, Settings). El diseño es moderno y adaptativo, utilizando radio buttons ocultos para manejar el estado de navegación.

- **Sección de comida (Food)**: Un catálogo de alimentos funcional con búsqueda en tiempo real mediante HTMX. Los usuarios pueden buscar alimentos, filtrarlos por categoría, y añadirlos a eventos de ingesta planificados.

- **Sistema de eventos de ingesta**: Capacidad de crear eventos de comida (planificados o consumidos), con soporte para múltiples comidas por día y diferentes tipos de comida (desayuno, almuerzo, comida, merienda, cena, snack, rescate).

- **Carrito de compras**: Una funcionalidad básica que muestra las comidas planificadas pendientes de consumir.

- **Catálogo de alimentos**: Una base de datos completa de alimentos con información nutricional detallada, incluyendo macronutrientes, Nutriscore, puntuación Nova y Yuka.

- **Registro manual de comidas**: Sistema para registrar comidas preparadas fuera de casa o de fuentes externas, con la capacidad de estimar valores nutricionales.

- **Sistema de recetas**: Estructura para guardar y reutilizar combinaciones de alimentos recurrentes.

- **Sistema de nevera**: Funcionalidad para gestionar sobras y alimentos preparados previamente, permitiendo su reutilización en futuras comidas.

### 2.3 Componentes Pendientes o en Desarrollo

Varias características importantes aún no están completamente implementadas:

- Integración con LibreView para importación automática de datos de glucosa.
- Integración con Apple Health para datos de actividad y salud.
- Panel de estadísticas y análisis de datos.
- Página de ajustes y configuración de usuario.
- Cálculo automático de incertidumbres en macronutrientes.
- Sistema de predicciones y recomendaciones.
- API de Open Food Facts para enriquecimiento de datos nutricionales.
- Sistema de autenticación de usuarios completo.
- Interfaz de confirmación de comida (cantidad ingerida real).

---

## 3. Arquitectura Técnica

### 3.1 Stack Tecnológico

El proyecto utiliza las siguientes tecnologías:

**Backend:**

- **Python**: Lenguaje de programación principal del proyecto.
- **FastHTML**: Framework web moderno basado en Python que permite crear aplicaciones web interactivas con facilidad. Utiliza un paradigma similar a HTMX pero con la potencia de Python.
- **PostgreSQL**: Sistema de gestión de base de datos relacional, elegido por su robustez, soporte para tipos de datos complejos y capacidades avanzadas de consultas.

**Frontend:**

- **Tailwind CSS**: Framework de utilidades CSS para el diseño de la interfaz de usuario. Proporciona un diseño moderno y responsivo con mínima escritura de CSS personalizado.
- **HTMX**: Librería JavaScript ligera que permite crear interfaces interactivas sin escribir JavaScript complejo. Las solicitudes HTTP parciales actualizan partes específicas de la página.
- **Alpine.js**: Framework JavaScript minimalista para manejar interactividad del lado del cliente.

**Infraestructura:**

- **Docker**: Contenedorización de la aplicación para facilitar el despliegue y la portabilidad.
- ** psycopg**: Biblioteca PostgreSQL para Python que permite la conexión y manipulación de la base de datos.

### 3.2 Estructura del Proyecto

El proyecto sigue una estructura modular organizada por funcionalidad:

```
DayBetes_food/
├── main.py                          # Punto de entrada de la aplicación
├── components/                      # Componentes UI reutilizables
│   ├── ui.py                        # Funciones helper de renderizado
│   ├── menu/                        # Componentes del menú de navegación
│   │   ├── menu_main.py             # Página principal del menú
│   │   ├── layout.py                # Layout de la isla flotante
│   │   └── sections.py              # Secciones del menú
│   ├── food/                        # Componentes relacionados con alimentos
│   │   ├── food_main.py            # Página principal de alimentos
│   │   └── alimentos.py             # Tarjetas y elementos de food
│   └── carrito/                     # Componentes del carrito
│       └── carrito_main.py          # Página del carrito
├── routes/                          # Definición de rutas de la aplicación
│   ├── main_routes.py              # Rutas principales
│   ├── food_routes.py              # Rutas de alimentos
│   └── carrito_routes.py           # Rutas del carrito
├── database/                        # Capa de acceso a datos
│   ├── connection.py               # Configuración de conexión a PostgreSQL
│   ├── schema.py                   # Definición del esquema de base de datos
│   ├── db_init.py                  # Inicialización de la base de datos
│   ├── __init__.py
│   └── queries/
│       └── crud.py                 # Operaciones CRUD centralizadas
└── static/                          # Archivos estáticos
    ├── css/
    │   ├── input.css               # Entrada de Tailwind
    │   └── output.css              # CSS compilado
    ├── js/
    │   └── logo_scroll.js          # Scripts JavaScript
    └── images/
        └── ui/                     # Iconos e imágenes de interfaz
```

### 3.3 Patrones de Diseño

El proyecto sigue varios patrones de diseño importantes:

**Patrón MVC (Model-View-Controller):** La separación entre la base de datos (modelo), los componentes UI (vista) y las rutas (controlador) permite mantener el código organizado y mantenible.

**Patrón Repository:** El archivo `crud.py` actúa como repositorio centralizado de todas las operaciones de base de datos, proporcionando una interfaz unificada para el acceso a datos.

**Patrón de Componentes:** Los elementos de la interfaz de usuario están encapsulados como funciones Python que devuelven componentes FastHTML, permitiendo su reutilización y composición.

**HTMX para Interactividad:** En lugar de escribir JavaScript complejo, la aplicación utiliza HTMX para manejar solicitudes asíncronas y actualizar partes específicas de la página, reduciendo significativamente la complejidad del frontend.

---

## 4. Sistema de Base de Datos

### 4.1 Esquema de Base de Datos

La base de datos PostgreSQL del proyecto contiene las siguientes tablas:

#### Tabla: usuario

Esta tabla almacena la información de los usuarios del sistema.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | SERIAL | Identificador único |
| nombre | VARCHAR(255) | Nombre del usuario |
| correo | VARCHAR(255) | Correo electrónico único |
| clave | TEXT | Contraseña (hasheada) |
| fecha_registro | TIMESTAMP | Fecha de creación de la cuenta |
| categoria | VARCHAR(255) | Tipo de usuario (admin/common) |

#### Tabla: catalogo

Almacena el catálogo de alimentos disponibles para seleccionar en las comidas.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | SERIAL | Identificador único |
| created_by | INTEGER | Usuario que creó el alimento |
| nombre | VARCHAR(255) | Nombre del producto |
| marca | VARCHAR(255) | Marca comercial |
| categoria | VARCHAR(100) | Categoría principal |
| subtipo | VARCHAR(100) | Subcategoría específica |
| estado_inicial | VARCHAR(50) | Estado físico del alimento |
| nutriscore | VARCHAR(1) | Puntuación Nutriscore (A-E) |
| NOVA | INTEGER | Clasificación Nova (1-4) |
| yuka | INTEGER | Puntuación Yuka (0-100) |
| porcion_default | INTEGER | Porción por defecto en gramos |
| calorias_100g | REAL | Calorías por 100g |
| hidratos_100g | REAL | Hidratos de carbono por 100g |
| azucares_100g | REAL | Azúcares por 100g |
| grasas_100g | REAL | Grasas por 100g |
| saturadas_100g | REAL | Grasas saturadas por 100g |
| proteinas_100g | REAL | Proteínas por 100g |
| fibra_100g | REAL | Fibra por 100g |
| cafeina | REAL | Contenido en cafeína |
| alcohol | REAL | Contenido en alcohol |
| cod_barras | VARCHAR | Código de barras |
| factor_cocinado | REAL | Factor para calcular peso en crudo |
| favorito | BOOLEAN | Marcador de favorito |

#### Tabla: ingesta_manual

Registro de comidas consumidas fuera de casa o de fuentes externas sin información nutricional exacta.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | SERIAL | Identificador único |
| created_by | INTEGER | Usuario que creó el registro |
| nombre | VARCHAR(255) | Nombre de la comida |
| descripcion | TEXT | Descripción del plato |
| subtipo | VARCHAR(100) | Categoría específica |
| procedencia | VARCHAR(255) | Origen (restaurante, casa, etc.) |
| cantidad_g | REAL | Cantidad en gramos |
| macronutrientes | REAL | Campos de información nutricional |
| indice_glucemico | VARCHAR(20) | IG estimado (alto/medio/bajo) |
| confianza_ig | INTEGER | Confianza en el IG (1-5) |
| favorito | BOOLEAN | Marcador de favorito |

#### Tabla: evento_ingesta

Representa una comida o evento de ingesta, ya sea planificado o consumido.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | SERIAL | Identificador único |
| user_id | INTEGER | Usuario asociado |
| estado | VARCHAR(20) | Estado (planificado/consumido) |
| tipo_comida | VARCHAR(50) | Tipo de comida |
| nombre | VARCHAR(255) | Nombre identificativo |
| hora_comida | TIMESTAMP | Fecha y hora de la comida |
| comida_fuera | BOOLEAN | Si se comió fuera |
| dosis_insulina | BOOLEAN | Si requiere insulina |
| cantidad_total | REAL | Cantidad total planificada |
| cantidad_ingerida | REAL | Cantidad realmente consumida |
| confianza_cantidad | REAL | Confianza en cantidad (0-1) |
| confianza_calidad | REAL | Confianza en calidad de macros |
| incertidumbre_hidratos | REAL | Incertidumbre en hidratos |
| incertidumbre_azucares | REAL | Incertidumbre en azúcares |
| incertidumbre_grasas | REAL | Incertidumbre en grasas |
| incertidumbre_saturadas | REAL | Incertidumbre en saturadas |
| incertidumbre_proteinas | REAL | Incertidumbre en proteínas |
| incertidumbre_fibra | REAL | Incertidumbre en fibra |
| notas | TEXT | Notas adicionales |

#### Tabla: porcion_detalle

Tabla de relación que conecta alimentos con eventos de ingesta, recetas o tuppers de nevera. Utiliza un patrón de arco (arc pattern) para relacionar un alimento con su destino.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | SERIAL | Identificador único |
| catalogo_id | INTEGER | Origen del catálogo |
| ingesta_manual_id | INTEGER | Origen de ingesta manual |
| evento_ingesta_id | INTEGER | Destino en evento |
| receta_id | INTEGER | Destino en receta |
| nunca_id | INTEGER | Destino en neverita |
| cantidad_g | REAL | Cantidad pesada |
| cocinado | VARCHAR(50) | Método de cocinado |
| conservacion | VARCHAR(50) | Método de conservación |
| estado_final | VARCHAR(50) | Estado final del alimento |
| pesado_estricto | BOOLEAN | Si se pesó exactamente |
| calidad_macros | BOOLEAN | Si los macros son exactos |
| cantidad_plato | REAL | Cantidad servida en plato |
| es_peso_cocinado | BOOLEAN | Si se pesó cocinado |
| offset_minutos | INTEGER | Diferencia horaria |

#### Tabla: recetas

Almacena recetas guardadas por el usuario.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | SERIAL | Identificador único |
| user_id | INTEGER | Usuario propietario |
| tipo_comida | VARCHAR(50) | Tipo de comida asociado |
| nombre | VARCHAR(255) | Nombre de la receta |
| notas | TEXT | Notas de la receta |
| favorito | BOOLEAN | Marcador de favorito |

#### Tabla: никогда

Gestiona los tuppers de comida preparada guardados en la neverita.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | SERIAL | Identificador único |
| user_id | INTEGER | Usuario propietario |
| nombre_tupper | VARCHAR(255) | Nombre identificativo |
| fecha_entrada | TIMESTAMP | Fecha de creación |
| es_compuesto | BOOLEAN | Si tiene varios ingredientes |
| peso_total_tupper | REAL | Peso total del tupper |

#### Tabla: etiquetas

Sistema de etiquetas para categorizar alimentos.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | SERIAL | Identificador único |
| nombre | VARCHAR(100) | Nombre único de la etiqueta |
| descripcion | TEXT | Descripción del significado |

#### Tabla: etiquetas_vinculadas

Tabla de relación muchos a muchos entre etiquetas y alimentos/recetas/ingestas manuales.

### 4.2 Sistema de Incertidumbres

Una característica distintiva del esquema es el sistema de cálculo automático de incertidumbres. Por cada macronutriente (hidratos, azúcares, grasas, saturadas, proteínas, fibra), se calcula un valor de incertidumbre entre 0 y 1 que representa la fiabilidad del dato. Este sistema utiliza una suma ponderada basada en las cantidades de cada ingrediente y si el dato es conocido o estimado.

---

## 5. Funcionalidades Implementadas

### 5.1 Navegación y UI

La aplicación cuenta con una interfaz de navegación moderna que incluye:

- **Isla Flotante (IslaFlotante)**: Un menú de navegación fijo en la parte inferior de la pantalla con cuatro opciones principales: Menu, Stats, Food y Settings. Utiliza un diseño de glas morphism con efecto blur.

- **Logo Animado**: Un logo fijo en la parte superior que sirve como elemento identificativo de la marca.

- **Botón de Carrito**: Un botón flotante que muestra el estado actual del carrito de compras y permite acceder rápidamente a él.

- **Diseño Responsivo**: La interfaz se adapta a diferentes tamaños de pantalla, con diferentes configuraciones para móvil, tablet y escritorio.

### 5.2 Catálogo de Alimentos

La funcionalidad de catálogo incluye:

- **Búsqueda en Tiempo Real**: Un campo de búsqueda que filtra los alimentos del catálogo mientras el usuario escribe, utilizando HTMX para actualizar la lista sin recargar la página.

- **Filtros**: Botones para filtrar el catálogo por diferentes criterios (todos, alimentos, recetas, favoritos).

- **Selector de Comida**: Un desplegable que permite seleccionar o crear una comida a la cual añadir alimentos.

- **Tarjetas de Alimento**: Cada alimento se muestra en una tarjeta con su nombre, contenido de hidratos de carbono y un botón para añadirlo a la comida seleccionada.

- **Añadir a Evento**: Los alimentos pueden añadirse a eventos de ingesta existentes o crear nuevos eventos.

### 5.3 Carrito de Compras

El sistema de carrito permite:

- **Ver Comidas Planificadas**: Muestra todas las comidas que están en estado "planificado" y aún no se han consumido.

- **Gestión de Estado**: Las comidas pueden cambiar de estado de planificado a consumido.

- **Información de Evento**: Cada evento muestra su identificador, estado actual y hora programada.

### 5.4 Acceso a Datos

El sistema incluye una capa completa de acceso a datos con funciones CRUD para todas las tablas:

- Operaciones de creación (INSERT)
- Operaciones de lectura (SELECT con filtros)
- Operaciones de actualización (UPDATE)
- Operaciones de eliminación (DELETE)
- Funciones específicas como obtener eventos del carrito, favoritos, etc.

---

## 6. Funcionalidades Pendientes de Desarrollo

### 6.1 Integración con Fuentes de Datos Externas

**LibreView Integration (Pendiente):**

- Importación automática de datos de glucosa minuto a minuto
- Importación de registros de insulina rápida y basal
- Captura de tendencias y velocidad de cambio de glucosa
- Información de zona de inyección y tiempos de espera
- Datos de corrección vs. comida

**Apple Health Integration (Pendiente):**

- Frecuencia cardíaca
- Heart Rate Variability (HRV) como indicador de estrés
- Datos de ejercicios (duración, tipo, intensidad)
- Datos de sueño (calidad, fases, duración)
- Otras métricas fisiológicas disponibles

### 6.2 Análisis y Estadísticas

**Panel de Estadísticas (Pendiente):**

- Gráficos de tendencia de glucosa
- Análisis de correlación entre alimentos y respuesta glucémica
- Estadísticas de tiempo en rango
- Comparativas de diferentes días y horarios
- Identificación de patrones temporales

### 6.3 Sistema de Recomendaciones

**Motor de Recomendaciones (Pendiente):**

- Algoritmo de aprendizaje automático personalizado
- Predicción de respuesta glucémica basada en alimentos, insulina y actividad
- Recomendaciones de dosis de insulina
- Sugerencias de timing de comidas
- Alertas de hipoglucemia e hiperglucemia

### 6.4 Enriquecimiento de Datos

**API de Open Food Facts (Pendiente):**

- Búsqueda automática de alimentos por código de barras
- Obtención de información nutricional enriquecida
- Integración de puntuaciones Nutriscore
- Integración de clasificaciones Nova
- Integración de datos de Yuka

### 6.5 Mejoras de Interfaz

- Página de ajustes y configuración de usuario
- Sistema de confirmación de comida detallado
- Cálculo automático de sobras y guardado en neverita
- Sistema de gestión de favoritos avanzado
- Interfaz de edición de eventos de ingesta

---

## 7. Próximos Pasos Recomendados

### 7.1 Prioridad Alta

1. **Completar la funcionalidad del carrito**: Permitir añadir alimentos con cantidades específicas, editar porciones y confirmar comidas consumidas.

2. **Implementar la página de estadísticas**: Crear visualizaciones de datos que permitan al usuario entender sus patrones glucémicos.

3. **Sistema de importación manual**: Permitir al usuario introducir datos de glucosa de forma manual mientras se prepara la integración automática.

### 7.2 Prioridad Media

4. **Integración con LibreView**: Desarrollar el connector para obtener datos de glucosa automáticamente.

5. **API de Open Food Facts**: Implementar la búsqueda y enriquecimiento automático de alimentos.

6. **Sistema de usuarios**: Completar el sistema de autenticación para soportar múltiples usuarios.

### 7.3 Prioridad Baja

7. **Apple Health Integration**: Integrar datos de actividad y sueño del Apple Watch.

8. **Motor de Machine Learning**: Desarrollar el modelo predictivo personalizado.

9. **Despliegue en producción**: Preparar la aplicación para producción con Docker y AWS.

---

## 8. Conclusiones

El proyecto DayBetes se encuentra en un estado de desarrollo activo con una base sólida. La arquitectura técnica está bien definida, el esquema de base de datos es completo y funcional, y los componentes principales de la interfaz de usuario están implementados. Sin embargo, queda un camino significativo por recorrer para alcanzar el objetivo final de un sistema de acompañamiento inteligente para personas diabéticas.

Las funcionalidades más críticas pendientes son el sistema de registro detallado de comidas (con cantidades, sobras y cálculo automático de incertidumbre), el panel de estadísticas, y la integración con fuentes de datos externas. Una vez estas funcionalidades estén operativas, el sistema podrá cumplir su propósito de facilitar el control diario de la diabetes y generar los datos necesarios para el análisis y la construcción del modelo de aprendizaje automático.

El enfoque incremental del proyecto, comenzando con un MVP funcional y expandiéndolo progresivamente, es adecuado para un proyecto de esta envergadura. La documentación de este estado actual servirá como referencia para planificar las siguientes fases de desarrollo y mantener un registro histórico del progreso del proyecto.
