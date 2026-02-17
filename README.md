# Estudio y Asistente de Diabetes Personalizado

> **Proyecto** centrado en la recolección, análisis y modelado de datos personales para la gestión de la diabetes tipo 1.

## Descripción del Proyecto

Este proyecto nace con el objetivo de entender y modelar la reacción glucémica de un individuo frente a diversos factores (nutricionales, fisiológicos y de actividad). En una primera fase, el estudio se centra en mis propios datos personales para, posteriormente, construir un **Modelo de Machine Learning** capaz de predecir comportamientos y actuar como un asistente diario.

El alcance final es desarrollar una aplicación web que facilite la recolección de datos, reduzca la carga mental del control de la enfermedad y ofrezca recomendaciones personalizadas basadas en patrones aprendidos.

## Objetivos

* **Análisis de Factores:** Estudiar cómo reacciona el organismo (glucosa) ante distintas variables (insulina, comida, deporte, estrés).
* **Modelado Predictivo:** Crear un algoritmo que aprenda de los hábitos y patrones específicos del usuario.
* **Desarrollo de Software:** Construir una **Web App** (Dashboard) que acompañe en el día a día y simplifique el registro de datos.
* **Escalabilidad:** Adaptar el algoritmo para que pueda generalizarse y beneficiar a otros pacientes diabéticos en el futuro.

## Fuentes de Datos

La arquitectura de datos integra tres fuentes principales para lograr una visión 360º del paciente:

### 1. LibreView (CGM & Insulina)
* **Monitorización:** Datos de glucosa minuto a minuto (valor, tendencia y velocidad de cambio).
* **Tratamiento:** Registros de insulina rápida y basal (bolis inteligentes).
* **Contexto:** Zona de inyección, tiempos de espera pre-comida, correcciones, etc.

### 2. Apple Watch (Salud & Actividad)
* **Fisiología:** Frecuencia cardíaca, HRV (Variabilidad de la frecuencia cardíaca como indicador de estrés)...
* **Sueño:** Calidad, fases, duración...
* **Ejercicio:** Duración, tipo de actividad, intensidad...

### 3. Dashboard Personal (Nutrición)
* **Registro de Comidas:** Macros (HC, Proteínas, Grasas, Fibra) y Micros (Saturadas, Azúcares).
* **Contexto:** Variables cualitativas (`come_fuera`, `pesado_estricto`, `cocinado`...) para evaluar la precisión del dato.
* **Enriquecimiento de Datos:** Integración con APIs (tipo **Open Food Facts**) para obtener Nutriscore y NOVA.
* **Bebidas:** Registro de alcohol, cafeína, refrescos, etc.

## Stack Tecnológico

El proyecto utiliza un stack moderno enfocado en rendimiento y simplicidad:

### Frontend & UI
* **FastHTML:** Para la estructura y renderizado rápido.
* **Tailwind CSS:** Diseño y estilos.
* **Alpine.js:** Interactividad y animaciones ligeras.

### Backend & Datos
* **PostgreSQL:** Base de datos relacional principal.
* **Python:** Lenguaje núcleo para el backend y análisis de datos.

### Infraestructura & DevOps
* **Docker:** Empaquetado y contenedorización de la aplicación.
* **AWS:** (Fase futura) Despliegue en la nube.

### Data Science (Fase Posterior)
* **Scikit-learn / TensorFlow:** Para el entrenamiento de modelos predictivos y análisis de patrones.

## Resultados Esperados

1.  **Académicos:** Obtención de *insights* profundos sobre la respuesta glucémica individual ante combinaciones complejas de variables.
2.  **Tecnológicos:** Un modelo de ML entrenado y una aplicación web funcional desplegada que actúe como "copiloto" en la gestión de la diabetes.

## Limitaciones y Retos

### Limitaciones Iniciales
Soy consciente de la ambición del proyecto. Grandes corporaciones (Abbott, Dexcom) poseen recursos ilimitados. Sin embargo, este proyecto busca la **hiper-personalización** y la **integración total de fuentes** (Nutrición + Wearables + CGM) que a menudo se encuentran en ecosistemas cerrados y separados.

### Retos Técnicos
* **Calidad del Dato:** Asegurar la precisión de los registros manuales (comida) frente a los automáticos (sensores).
* **Complejidad del Modelo:** Modelar un sistema biológico caótico con múltiples variables de confusión.
* **Integración:** Unificar formatos de datos heterogéneos (series temporales de glucosa vs. eventos puntuales de comidas).

---
*Autor: Pablo Lucas Mora*
