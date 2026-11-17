# Proyecto Integrador - Almacenes y Minería de Datos

**Anticipación de saturación y recomendación de rutas alternas en la red del STC Metro y Metrobús de la CDMX**

Facultad de Ciencias, UNAM · Profesora: Jessica Santizo Galicia
Ayudante de teoría: Diego Antonio Villalba González · Ayudante de laboratorio: Emma Alicia Jiménez Sánchez

## 🌐 Sitio desplegado

**https://fernando-bm.github.io/Proyecto_Mineria_Datos**

## Equipo

| Integrante |
|------------|
| Aldair Coronel Ruiz | 
| Fernando Bernal Martínez |
| Luis Alberto Hernández Aguilar | 
| Tania Ramírez Plascencia |

## Entregas

| # | Fase CRISP-DM | Entrega | Estado |
|---|---------------|---------|--------|
| 1 | Comprensión del negocio | E0 | ✅ |
| 2 | Comprensión de los datos | E1 | ✅ |
| 3 | Comprensión (cierre) y preparación de los datos | E2 | ✅ |
| 4 | Modelado | E3 | ⏳ |
| 5 | Evaluación | E4 | ⏳ |
| 6 | Despliegue | Reporte y presentación final | ⏳ |

### E0 - Comprensión del Negocio

| Página | Archivo |
|--------|---------|
| Bitácora del stakeholder | `entregas/E0_comprension_negocio/bitacora.qmd` |
| Business Understanding Canvas | `entregas/E0_comprension_negocio/canvas.qmd` |
| Preguntas de investigación | `entregas/E0_comprension_negocio/preguntas.qmd` |
| Criterio de éxito | `entregas/E0_comprension_negocio/criterio_exito.qmd` |
| Supuestos y riesgos | `entregas/E0_comprension_negocio/riesgos_supuestos.qmd` |
| Uso de herramientas de IA | `entregas/E0_comprension_negocio/uso_ia.qmd` |
| Fuentes consultadas | `entregas/E0_comprension_negocio/fuentes.qmd` |

### E1 - Arquitectura del Data Warehouse

| Página | Archivo |
|--------|---------|
| Fuentes de datos (búsqueda, catálogo e integración) | `entregas/E1_arquitectura_dw/fuentes.qmd` |
| Arquitectura de tres capas (staging → DW → DataMart) | `entregas/E1_arquitectura_dw/arquitectura.qmd` |
| Esquema estrella (grano, diagrama y DDL) | `entregas/E1_arquitectura_dw/estrella.qmd` |
| Matriz de trazabilidad | `entregas/E1_arquitectura_dw/trazabilidad.qmd` |
| Uso de herramientas de IA | `entregas/E1_arquitectura_dw/uso_ia.qmd` |
| SQL (datasets, perfilado, DDL, DataMart) | `entregas/E1_arquitectura_dw/sql/` |

No hubo pivote: el grano disponible (estación-línea × día) coincide con el objetivo de minería de E0.

### E2 - EDA y Preparación de Datos

| Página | Archivo |
|--------|---------|
| Análisis exploratorio (descriptiva, Gini, entropía, hallazgos) | `entregas/E2_eda_preparacion/eda.qmd` |
| Preparación (limpieza, reducción, muestreo, antes/después) | `entregas/E2_eda_preparacion/preparacion.qmd` |
| Pipeline reproducible, DW poblado y DataMart | `entregas/E2_eda_preparacion/pipeline.qmd` |
| Decisiones en lenguaje no técnico | `entregas/E2_eda_preparacion/decisiones.qmd` |
| Matriz de trazabilidad extendida | `entregas/E2_eda_preparacion/trazabilidad.qmd` |
| Ajustes a E1 (E1 v2) | `entregas/E2_eda_preparacion/ajustes.qmd` |
| Uso de herramientas de IA | `entregas/E2_eda_preparacion/uso_ia.qmd` |
| Pipeline (punto de entrada, configuración, código, muestra) | `pipeline/` |
| SQL v2 (DDL, DataMart, validaciones, resultados) | `sql/` |

**Reproducir E2:** `pip install -r pipeline/requirements.txt` y `python pipeline/run_pipeline.py` (BigQuery), o `python pipeline/run_pipeline.py --fuente muestra` (sin credenciales, ~10 s). Instrucciones completas en [`pipeline/README.md`](pipeline/README.md); también se puede correr en Google Colab con `pipeline/ejecutar_en_colab.ipynb`.

Sin pivote: los ajustes (E1 v2) agregan sismos y eventos masivos, quitan una variable redundante y corrigen el tratamiento de los ceros; el objetivo y el criterio de éxito de E0 no cambian.

## Estructura del repositorio

```
Proyecto_Mineria_Datos/
├── _quarto.yml                    # configuración del sitio (output-dir: docs)
├── index.qmd                      # portada
├── styles.css                     # estilos, incluido el Canvas
├── entregas/
│   ├── E0_comprension_negocio/
│   │   ├── bitacora.qmd
│   │   ├── canvas.qmd
│   │   ├── preguntas.qmd
│   │   ├── criterio_exito.qmd
│   │   ├── riesgos_supuestos.qmd
│   │   ├── uso_ia.qmd
│   │   ├── fuentes.qmd
│   │   └── fuentes/               # evidencia archivada del stakeholder simulado
│   ├── E1_arquitectura_dw/
│   │   ├── fuentes.qmd            # búsqueda, catálogo e integración
│   │   ├── arquitectura.qmd       # 3 capas, evidencia BigQuery, DataMart
│   │   ├── estrella.qmd           # grano, diagrama Mermaid y DDL
│   │   ├── trazabilidad.qmd       # matriz pregunta-métrica-dimensión-fuente
│   │   ├── uso_ia.qmd
│   │   ├── sql/                   # versión original de E1 (sin cambios)
│   │   ├── staging/               # descarga reproducible de las fuentes API
│   │   └── img/                   # capturas de BigQuery
│   └── E2_eda_preparacion/
│       ├── eda.qmd                # estadística, Gini/entropía, figuras, hallazgos
│       ├── preparacion.qmd        # calidad, reducción, muestreo, antes/después
│       ├── pipeline.qmd           # arquitectura del pipeline y carga al DW
│       ├── decisiones.qmd         # documento no técnico
│       ├── trazabilidad.qmd       # matriz extendida
│       ├── ajustes.qmd            # E1 v2
│       ├── uso_ia.qmd
│       ├── tablas/                # tablas que genera el pipeline (.md y .csv)
│       └── img/                   # figuras que genera el pipeline
├── pipeline/
│   ├── README.md                  # instalación, autenticación y ejecución
│   ├── run_pipeline.py            # punto de entrada
│   ├── config.yaml                # parámetros: umbrales, semilla, datasets
│   ├── requirements.txt           # versiones fijadas
│   ├── ejecutar_en_colab.ipynb    # corrida en Google Colab
│   ├── src/                       # ingesta, calidad, limpieza, reducción, muestreo, verificación, carga
│   └── data/                      # sample/ (muestra pequeña) y fuentes/ (sismos USGS)
├── sql/                           # E1 v2: ddl_dw, consultas_mart, validaciones_dw, resultados_mart
├── datos/crudos/                  # CSV/ZIP del portal (no se versionan)
├── docs/                          # sitio compilado (lo genera Quarto)
└── README.md
```
