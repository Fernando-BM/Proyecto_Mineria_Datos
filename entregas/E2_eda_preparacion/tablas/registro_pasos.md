| paso | filas_entrada | filas_salida | segundos | nota |
|---|---|---|---|---|
| ingesta | 1,252,554 | 1,252,554 | 55.4 | origen=bigquery |
| calidad | 1,180,920 | 1,180,920 | 21 | dataset analítico crudo: 1,180,920 × 13 |
| limpieza | 1,252,554 | 1,227,751 | 23.4 | metro 1,180,920 · metrobús 34,505 · estaciones 195 |
| reduccion | 1,180,920 | 303,385 | 7.900 | dataset analítico 2022+ en operación: 303,385 filas × 36 columnas |
| muestreo | 1,180,920 | 1,180,920 | 3.600 | población completa; muestra solo para el repositorio |
| verificacion | 1,180,920 | 1,119,000 | 7.800 | estación-días en operación y medidos |
| modelo | 1,227,751 | 1,228,159 | 2.900 | esquema estrella E1 v2 |
| carga | 1,228,159 | 1,228,159 | 53.3 | destino=bigquery |
