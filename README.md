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
| 3 | Preparación de los datos | E2 | ⏳ |
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
│   └── E1_arquitectura_dw/
│       ├── fuentes.qmd            # búsqueda, catálogo e integración
│       ├── arquitectura.qmd       # 3 capas, evidencia BigQuery, DataMart
│       ├── estrella.qmd           # grano, diagrama Mermaid y DDL
│       ├── trazabilidad.qmd       # matriz pregunta-métrica-dimensión-fuente
│       ├── uso_ia.qmd
│       ├── sql/                   # 00_datasets, 01_perfilado, ddl_dw, consultas_mart
│       ├── staging/               # descarga reproducible de las fuentes API
│       └── img/                   # capturas de BigQuery
├── docs/                          # sitio compilado (lo genera Quarto)
└── README.md
```
