| prueba | valor | esperado | resultado |
|---|---|---|---|
| 01 filas dim_fecha | 6,056 | 6,056 | OK |
| 02 filas dim_linea | 19 | 19 | OK |
| 03 filas dim_estacion | 603 | 603 | OK |
| 04 filas dim_clima | 6,056 | 6,056 | OK |
| 05 filas hechos_afluencia_metro | 1,180,920 | 1,180,920 | OK |
| 06 filas hechos_afluencia_metrobus | 34,505 | 34,505 | OK |
| 07 grano metro (fecha_key, estacion_key): filas repetidas | 0 | 0 | OK |
| 08 grano metro (fecha, estación-línea natural): filas repetidas | 0 | 0 | OK |
| 09 grano metrobús (fecha_key, linea_key): filas repetidas | 0 | 0 | OK |
| 10 metro: llaves nulas | 0 | 0 | OK |
| 11 metro: fecha_key huérfanas | 0 | 0 | OK |
| 12 metro: estacion_key huérfanas | 0 | 0 | OK |
| 13 metro: linea_key huérfanas | 0 | 0 | OK |
| 14 metro: clima_key huérfanas | 0 | 0 | OK |
| 15 metrobús: fecha_key huérfanas | 0 | 0 | OK |
| 16 metrobús: linea_key huérfanas | 0 | 0 | OK |
| 17 metro: hechos fuera de la vigencia de su versión | 0 | 0 | OK |
| 18 dim_estacion: estaciones sin exactamente una versión vigente | 0 | 0 | OK |
| 19 metro: afluencia negativa | 0 | 0 | OK |
| 20 metrobús: afluencia negativa | 0 | 0 | OK |
