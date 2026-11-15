| paso | filas_entrada | filas_salida | segundos | nota |
|---|---|---|---|---|
| ingesta | 1,252,554 | 1,252,554 | 0.700 | origen=local |
| calidad | 1,180,920 | 1,180,920 | 6.100 | dataset analítico crudo: 1,180,920 × 13 |
| limpieza | 1,252,554 | 1,227,751 | 7.300 | metro 1,180,920 · metrobús 34,505 · estaciones 195 |
| reduccion | 1,180,920 | 303,385 | 3.000 | dataset analítico 2022+ en operación: 303,385 filas × 36 columnas |
| muestreo | 1,180,920 | 1,180,920 | 1.200 | población completa; muestra solo para el repositorio |
| verificacion | 1,180,920 | 1,119,000 | 2.600 | estación-días en operación y medidos |
| modelo | 1,227,751 | 1,228,159 | 1.300 | esquema estrella E1 v2 |
| carga | 1,228,159 | 1,228,159 | 1.500 | destino=local |
