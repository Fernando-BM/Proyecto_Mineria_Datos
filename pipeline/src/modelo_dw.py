"""Construye las tablas del esquema estrella (E1 v2) a partir de los datos
limpios: dimensiones con llaves sustitutas y hechos al grano declarado.
Incluye las validaciones automáticas (asserts) del modelo."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from .limpieza import ORDEN_METRO
from .utiles import LOG

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
FIN_VIGENCIA = dt.date(9999, 12, 31)


def clave_fecha(s: pd.Series) -> pd.Series:
    return (s.dt.year * 10000 + s.dt.month * 100 + s.dt.day).astype("int64")


def dim_fecha(cal: pd.DataFrame) -> pd.DataFrame:
    f = cal["fecha"]
    d = pd.DataFrame({
        "fecha_key": clave_fecha(f),
        "fecha": f.dt.date,
        "anio": f.dt.year, "mes": f.dt.month,
        "nombre_mes": f.dt.month.map(lambda m: MESES[m - 1]),
        "dia": f.dt.day,
        "dia_semana_num": f.dt.dayofweek + 1,
        "nombre_dia": f.dt.dayofweek.map(lambda x: DIAS[x]),
        "semana_iso": f.dt.isocalendar().week.astype("int64").values,
        "es_fin_de_semana": f.dt.dayofweek >= 5,
        "es_dia_quincena": (f.dt.day == 15) | f.dt.is_month_end,
        "es_festivo_oficial": cal["es_festivo_oficial"].astype(bool),
        "nombre_festivo": cal["nombre_festivo"],
        "es_semana_santa": cal["es_semana_santa"].astype(bool),
        "es_dia_sin_medicion": cal["es_dia_sin_medicion"].astype(bool),
        "es_dia_sismo": cal["es_dia_sismo"].astype(bool),
        "sismo_magnitud_max": cal["sismo_magnitud_max"].astype(float),
        "evento_masivo": cal["evento_masivo"],
    })
    return d


def dim_linea(lineas: pd.DataFrame) -> pd.DataFrame:
    d = lineas.copy()
    d.insert(0, "linea_key", np.arange(1, len(d) + 1, dtype="int64"))
    return d[["linea_key", "sistema", "linea_codigo", "nombre_linea", "terminales", "color_hex",
              "gtfs_route_id"]]


def versiones_estacion(metro: pd.DataFrame, cat: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """SCD tipo 2: una versión por cada tramo continuo de estado_servicio."""
    m = metro[["fecha", "linea_codigo", "estacion", "estado_servicio"]].copy()
    m["_orden_linea"] = m["linea_codigo"].map({c: i for i, c in enumerate(ORDEN_METRO)})
    m = m.sort_values(["_orden_linea", "estacion", "fecha"])
    cambio = (m["estado_servicio"] != m.groupby(["linea_codigo", "estacion"])["estado_servicio"].shift())
    m["_version"] = cambio.cumsum()
    v = (m.groupby("_version")
          .agg(linea_codigo=("linea_codigo", "first"), estacion=("estacion", "first"),
               estado_servicio=("estado_servicio", "first"),
               fecha_inicio_vigencia=("fecha", "min"), fecha_fin=("fecha", "max"))
          .reset_index())
    v["estacion_key"] = np.arange(1, len(v) + 1, dtype="int64")
    ultimo = v.groupby(["linea_codigo", "estacion"])["fecha_fin"].transform("max") == v["fecha_fin"]
    v["es_version_vigente"] = ultimo
    v["fecha_fin_vigencia"] = [FIN_VIGENCIA if u else f.date() for u, f in zip(ultimo, v["fecha_fin"])]
    v = v.merge(cat, left_on=["linea_codigo", "estacion"], right_on=["linea_codigo", "nombre_en_fuente"],
                how="left", validate="many_to_one")
    assert v["gtfs_stop_id"].notna().all()
    llave = m["_version"].map(v.set_index("_version")["estacion_key"])
    dim = pd.DataFrame({
        "estacion_key": v["estacion_key"],
        "estacion_nk": v["estacion_nk"],
        "gtfs_stop_id": v["gtfs_stop_id"],
        "nombre_oficial": v["nombre_oficial"],
        "nombre_en_fuente": v["nombre_en_fuente"],
        "linea_codigo": v["linea_codigo"],
        "latitud": v["latitud"].astype(float),
        "longitud": v["longitud"].astype(float),
        "es_correspondencia": v["es_correspondencia"].astype(bool),
        "estado_servicio": v["estado_servicio"],
        "fecha_inicio_vigencia": pd.to_datetime(v["fecha_inicio_vigencia"]).dt.date,
        "fecha_fin_vigencia": v["fecha_fin_vigencia"],
        "es_version_vigente": v["es_version_vigente"].astype(bool),
    })
    return dim, llave.reindex(metro.index)


def dim_clima(clima: pd.DataFrame, fecha_descarga: str | None) -> pd.DataFrame:
    return pd.DataFrame({
        "clima_key": clave_fecha(clima["fecha"]),
        "fecha": clima["fecha"].dt.date,
        "precipitacion_mm": clima["precipitacion_mm"].astype(float),
        "temp_max_c": clima["temp_max_c"].astype(float),
        "temp_min_c": clima["temp_min_c"].astype(float),
        "categoria_lluvia": clima["categoria_lluvia"],
        "fecha_descarga": pd.Timestamp(fecha_descarga).date() if fecha_descarga else None,
    })


def construir(limpio: dict, cfg: dict) -> dict:
    metro, mb = limpio["metro"], limpio["metrobus"]
    df_ = dim_fecha(limpio["calendario"])
    dl = dim_linea(limpio["lineas"])
    de, llave_est = versiones_estacion(metro, limpio["estaciones"])
    dc = dim_clima(limpio["clima"], cfg.get("fecha_descarga_clima", "2026-10-01"))

    lk_metro = dl[dl.sistema == "Metro"].set_index("linea_codigo")["linea_key"]
    lk_mb = dl[dl.sistema == "Metrobús"].set_index("linea_codigo")["linea_key"]
    claves_clima = set(dc["clima_key"])

    fk = clave_fecha(metro["fecha"])
    hm = pd.DataFrame({
        "fecha_key": fk,
        "estacion_key": llave_est.astype("int64"),
        "linea_key": metro["linea_codigo"].map(lk_metro).astype("int64"),
        "clima_key": fk.where(fk.isin(claves_clima)).astype("Int64"),
        "afluencia": metro["afluencia"].astype("Int64"),
        "es_registro_cero": metro["es_registro_cero"].astype(bool),
        "es_atipico": metro["es_atipico"].astype(bool),
    }).sort_values(["estacion_key", "fecha_key"]).reset_index(drop=True)

    fkb = clave_fecha(mb["fecha"])
    hb = pd.DataFrame({
        "fecha_key": fkb,
        "linea_key": mb["linea_codigo"].map(lk_mb).astype("int64"),
        "clima_key": fkb.where(fkb.isin(claves_clima)).astype("Int64"),
        "afluencia": mb["afluencia"].astype("Int64"),
    }).sort_values(["linea_key", "fecha_key"]).reset_index(drop=True)

    tablas = {"dim_fecha": df_, "dim_linea": dl, "dim_estacion": de, "dim_clima": dc,
              "hechos_afluencia_metro": hm, "hechos_afluencia_metrobus": hb}
    validar(tablas, cfg)
    return tablas


# ---------------------------------------------------------------------
# Validaciones automáticas
# ---------------------------------------------------------------------
def validar(t: dict, cfg: dict) -> pd.DataFrame:
    filas = []

    def chequeo(nombre: str, ok: bool, detalle) -> None:
        filas.append({"validacion": nombre, "resultado": "OK" if ok else "FALLA", "detalle": detalle})
        if not ok:
            raise AssertionError(f"Validación fallida: {nombre} ({detalle})")

    pk = {"dim_fecha": ["fecha_key"], "dim_linea": ["linea_key"], "dim_estacion": ["estacion_key"],
          "dim_clima": ["clima_key"], "hechos_afluencia_metro": ["fecha_key", "estacion_key"],
          "hechos_afluencia_metrobus": ["fecha_key", "linea_key"]}
    for tabla, cols in pk.items():
        d = t[tabla]
        chequeo(f"{tabla}: llave primaria sin nulos", bool(d[cols].notna().all().all()), f"{len(d):,} filas")
        chequeo(f"{tabla}: llave primaria única (grano)", not d.duplicated(cols).any(),
                f"{len(d):,} filas = {len(d.drop_duplicates(cols)):,} combinaciones distintas")

    hm, hb = t["hechos_afluencia_metro"], t["hechos_afluencia_metrobus"]
    for hecho, d in [("hechos_afluencia_metro", hm), ("hechos_afluencia_metrobus", hb)]:
        for col, dim in [("fecha_key", "dim_fecha"), ("linea_key", "dim_linea"), ("clima_key", "dim_clima")]:
            huerf = (~d[col].dropna().isin(t[dim][col])).sum()
            chequeo(f"{hecho}.{col}: sin llaves huérfanas", huerf == 0, f"{huerf} huérfanas")
    huerf = (~hm["estacion_key"].isin(t["dim_estacion"]["estacion_key"])).sum()
    chequeo("hechos_afluencia_metro.estacion_key: sin llaves huérfanas", huerf == 0, f"{huerf} huérfanas")

    e = t["dim_estacion"].merge(hm.groupby("estacion_key")["fecha_key"].agg(["min", "max"]),
                                left_on="estacion_key", right_index=True)
    ini_ok = (pd.to_datetime(e["fecha_inicio_vigencia"]).dt.strftime("%Y%m%d").astype(int) == e["min"]).all()
    chequeo("hechos ↔ dim_estacion: cada fila cae en la versión vigente ese día", bool(ini_ok),
            f"{len(e)} versiones")
    vig = t["dim_estacion"].groupby("estacion_nk")["es_version_vigente"].sum()
    chequeo("dim_estacion: exactamente una versión vigente por estación", bool((vig == 1).all()),
            f"{len(vig)} estaciones")
    grano = hm.merge(t["dim_estacion"][["estacion_key", "estacion_nk"]], on="estacion_key")
    chequeo("hechos_afluencia_metro: grano estación-línea × día único",
            not grano.duplicated(["fecha_key", "estacion_nk"]).any(),
            f"{grano['estacion_nk'].nunique()} estaciones-línea")
    chequeo("afluencia >= 0", bool((hm["afluencia"].dropna() >= 0).all() and
                                    (hb["afluencia"].dropna() >= 0).all()), "Metro y Metrobús")
    dias = len(t["dim_fecha"])
    if cfg.get("_modo_muestra"):
        esperado_m = hm["fecha_key"].nunique() * cfg["esperado"]["estaciones_linea"]
    else:
        esperado_m = dias * cfg["esperado"]["estaciones_linea"]
    chequeo("hechos_afluencia_metro: filas = días × 195", len(hm) == esperado_m,
            f"{len(hm):,} = {esperado_m:,}")
    chequeo("precipitación >= 0 y mínima <= máxima",
            bool((t["dim_clima"]["precipitacion_mm"] >= 0).all() and
                 (t["dim_clima"]["temp_min_c"] <= t["dim_clima"]["temp_max_c"]).all()), "dim_clima")
    LOG.info("  validaciones del modelo: %d de %d OK", sum(f["resultado"] == "OK" for f in filas), len(filas))
    t["_validaciones"] = pd.DataFrame(filas)
    return t["_validaciones"]
