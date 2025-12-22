# TFG: Estudio de Diabetes Personalizado

Este proyecto consiste en un estudio de diabetes personalizado sobre mis datos personales, para en una fase posterior construir un modelo que te ayude en el día a día en función de tus características personales.

## 🎯 Objetivo
El objetivo principal es el de entender y estudiar cómo reacciona una persona a distintos factores en su control de la glucosa (El estudio va a consistir en estudiar los datos de un solo individuo). Una vez estudiado esto se pretende construir un modelo que aprenda de hábitos y patrones de esta persona, para poder acompañar y actuar como un acompañante en el día a día de la diabetes. 

Quiero además construir una página que acompañe en este proyecto en la recolección de datos, para poder facilitar y disminuir la carga de llevar un control diario de tantos factores de los que depende esta enfermedad. Por último me he propuesto tratar de adaptar este algoritmo y aplicación a más gente, para que más personas diabéticas se puedan beneficiar de los resultados de esta investigación (El algoritmo quiero que aprenda de cada usuario, para así hacer las mejores recomendaciones posibles). 

## 🚀 Alcance
El alcance como he mencionado es poder construir una aplicación que acompañe a personas diabéticas en su día a día, para así conseguir facilitar sus vidas. Esta funcionará con un algoritmo personalizado que aprenderá de los datos de cada individuo, para poder adaptarse mejor.

## 📊 Fuentes de datos
En cuanto a las fuentes de datos, me voy a basar en las siguientes:

* **LibreView:** Esta página contiene los datos de glucosa minuto a minuto (valor, tendencia y velocidad), además de los registros de insulina rápida y basal (En caso de tener dos bolis inteligentes) con zona de inyección, espera antes de la comida, si es corrección o no…, todos estos con la hora exacta de la medición o aplicación.
* **Apple Watch:** Haré uso del Apple Watch para tener en cuenta todas las variables de actividad y fisiológicas. Recolectaré a través de Apple Health datos de la frecuencia cardiaca, Heart Rate Variability (Estrés), Ejercicios (duración, tipo, intensidad…), sueño (calidad, fases, duración…).
* **Página personal:** A través de un dashboard sencillo e intuitivo, haré un registro de las comidas, con los valores de Hidratos, Proteínas, Azúcares, Grasas y Fibra, además de algunas variables como `come_fuera` o `es_pesado` para evaluar la calidad y precisión de las medidas. Además me ayudaré de la API de Open Food Facts para sacar valores de comidas registradas (con valores específicos como categorización Nutriscore y NOVA), y otras funcionalidades para facilitar el registro. También incluiré valores de bebidas (refrescos, zumos, alcohol, cafeína…).

## 📅 Fases del estudio

| Fase Principal | Duración Estimada | Tareas Clave |
| :--- | :--- | :--- |
| **Fase preparación para el estudio** | 2 meses | Preparación de dashboard para registro de datos, y de todos los factores a controlar durante el estudio. |
| **Estudio y recolección de datos** | 2 meses | Recolección de los datos. |
| **Fase de análisis inicial** | 1 mes | Comenzamos la limpieza y análisis exploratorio de la base de datos. |
| **Preparación modelo** | 3 meses | Investigación profunda de la base de datos y preparación del modelo a usar. |
| **Control de calidad y precisión** | 3 meses | Pruebas de usabilidad de la aplicación y precisión del modelo. Recolección de feedback y ajustes finales. |
| **Documentación y Presentación** | 3 meses | Redacción de la memoria del TFG. Preparación de la presentación. |

## 🛠️ Requisitos y Tecnología
* **Tecnologías Clave:** Listado de las herramientas, lenguajes de programación (Python, R, JavaScript), bibliotecas (Pandas, Scikit-learn, TensorFlow), y frameworks que se utilizarán (p. ej., React, Flask, Flutter).
* **Requisitos del Sistema:** Hardware o software necesario para el desarrollo y despliegue.

## 🏆 Resultados Esperados
* **Científicos/Académicos:** La obtención de insights sobre la respuesta glucémica del individuo a diversos factores.
* **Tecnológicos:** El modelo de machine learning personalizado y la aplicación funcional que actúe como acompañante.

## ⚠️ Limitaciones y Retos
* **Limitaciones Iniciales:** Reconozco que es un proyecto ambicioso, que contiene dificultades en cuanto a los datos, y la generalización.
* **Retos Técnicos:** Problemas potenciales en la calidad de los datos, la complejidad de los modelos o la integración de sistemas.
