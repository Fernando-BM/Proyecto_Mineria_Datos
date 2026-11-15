"""Utilidades compartidas: configuración, rutas, registro por paso,
tablas en Markdown, figuras y medidas (Gini, entropía)."""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import os
import time
import unicodedata
import re
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

RAIZ = Path(__file__).resolve().parents[2]          # raíz del repositorio
LOG = logging.getLogger("pipeline")


# ---------------------------------------------------------------------
# Configuración y rutas
# ---------------------------------------------------------------------
def cargar_config(ruta: str | Path = "pipeline/config.yaml") -> dict:
    with open(RAIZ / ruta, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    proyecto = os.environ.get("GCP_PROJECT")
    if proyecto:
        cfg["bigquery"]["proyecto"] = proyecto
    return cfg


def ruta(rel: str | Path) -> Path:
    """Ruta absoluta a partir de una ruta relativa a la raíz del repo."""
    p = RAIZ / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


# ---------------------------------------------------------------------
# Registro de ejecución y de limpieza
# ---------------------------------------------------------------------
def configurar_log(cfg: dict) -> None:
    LOG.setLevel(logging.INFO)
    LOG.handlers.clear()
    fmt = logging.Formatter("%(asctime)s | %(message)s", "%H:%M:%S")
    consola = logging.StreamHandler()
    consola.setFormatter(fmt)
    archivo = logging.FileHandler(ruta(cfg["salidas"]["log"]), mode="w", encoding="utf-8")
    archivo.setFormatter(fmt)
    LOG.addHandler(consola)
    LOG.addHandler(archivo)


class Registro:
    """Acumula (1) filas de entrada/salida por paso y (2) el registro de
    limpieza: qué problema, cuántas filas o celdas, qué decisión y por qué."""

    def __init__(self) -> None:
        self.pasos: list[dict] = []
        self.limpieza: list[dict] = []
        self._t0: dict[str, float] = {}

    def inicio(self, paso: str) -> None:
        self._t0[paso] = time.time()
        LOG.info("=" * 60)
        LOG.info("PASO %s", paso.upper())

    def fin(self, paso: str, entrada: int, salida: int, nota: str = "") -> None:
        seg = time.time() - self._t0.get(paso, time.time())
        self.pasos.append({"paso": paso, "filas_entrada": entrada, "filas_salida": salida,
                           "segundos": round(seg, 1), "nota": nota})
        LOG.info("%s: %s filas de entrada -> %s de salida (%.1f s) %s",
                 paso, f"{entrada:,}", f"{salida:,}", seg, nota)

    def limpiar(self, tabla: str, problema: str, variable: str, afectadas: int,
                total: int, decision: str, justificacion: str) -> None:
        pct = 100 * afectadas / total if total else 0.0
        self.limpieza.append({
            "id": f"L{len(self.limpieza) + 1:02d}", "tabla": tabla, "problema": problema,
            "variable": variable, "afectadas": int(afectadas), "total": int(total),
            "%": round(pct, 3), "decisión": decision, "justificación": justificacion})
        LOG.info("  [limpieza] %s · %s: %s de %s (%.3f %%) -> %s",
                 tabla, problema, f"{afectadas:,}", f"{total:,}", pct, decision)


# ---------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------
def reparar_codificacion(s: str) -> str:
    """Repara texto UTF-8 leído como Latin-1 ('LÃ­nea' -> 'Línea')."""
    if not isinstance(s, str) or ("Ã" not in s and "Â" not in s):
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def clave_texto(s: str) -> str:
    """Clave de comparación: sin acentos, minúsculas, solo letras y dígitos."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s)


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]+", "_", s).strip("_")


# ---------------------------------------------------------------------
# Salidas: Markdown y figuras
# ---------------------------------------------------------------------
def _fmt(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NA:
        return "—"
    if isinstance(v, (bool, np.bool_)):
        return "sí" if v else "no"
    if isinstance(v, (int, np.integer)):
        return f"{int(v):,}"
    if isinstance(v, (float, np.floating)):
        a = abs(v)
        if a == 0:
            return "0"
        if a >= 10 and float(v).is_integer():
            return f"{int(v):,}"
        if a >= 1000:
            return f"{v:,.0f}"
        if a >= 10:
            return f"{v:,.1f}"
        if a >= 0.001:
            return f"{v:.3f}"
        return f"{v:.2e}"
    if isinstance(v, (pd.Timestamp, dt.date)):
        return str(v)[:10]
    return str(v).replace("|", "\\|").replace("\n", " ")


def tabla_md(df: pd.DataFrame, nombre: str, cfg: dict, csv: bool = True,
             indice: bool = False) -> Path:
    """Escribe la tabla en Markdown (para incluir en Quarto) y en CSV."""
    d = (df.reset_index() if indice else df).copy()
    for c in d.columns:
        if str(c).lower() in {"año", "anio", "year"}:
            d[c] = d[c].astype(str)
    cab ="| " + " | ".join(str(c) for c in d.columns) + " |"
    sep = "|" + "|".join("---" for _ in d.columns) + "|"
    filas = ["| " + " | ".join(_fmt(v) for v in fila) + " |" for fila in d.itertuples(index=False)]
    destino = ruta(Path(cfg["salidas"]["tablas"]) / f"{nombre}.md")
    destino.write_text("\n".join([cab, sep, *filas]) + "\n", encoding="utf-8")
    if csv:
        d.to_csv(destino.with_suffix(".csv"), index=False)
    return destino


def guardar_figura(fig, nombre: str, cfg: dict) -> Path:
    destino = ruta(Path(cfg["salidas"]["figuras"]) / f"{nombre}.png")
    fig.savefig(destino, dpi=150, bbox_inches="tight", metadata={"Software": None})
    import matplotlib.pyplot as plt
    plt.close(fig)
    return destino


# ---------------------------------------------------------------------
# Medidas de concentración y heterogeneidad
# ---------------------------------------------------------------------
def gini(x) -> float:
    """G = sum_i sum_j |xi - xj| / (2 n^2 media), con la fórmula equivalente
    sobre los valores ordenados. Requiere x >= 0."""
    x = np.sort(np.asarray(x, dtype=float))
    x = x[~np.isnan(x)]
    n = x.size
    if n == 0 or x.sum() == 0:
        return np.nan
    if (x < 0).any():
        raise ValueError("Gini requiere valores no negativos")
    i = np.arange(1, n + 1)
    return float((2 * np.sum(i * x)) / (n * x.sum()) - (n + 1) / n)


def lorenz(x) -> tuple[np.ndarray, np.ndarray]:
    x = np.sort(np.asarray(x, dtype=float))
    x = x[~np.isnan(x)]
    acum = np.concatenate([[0], np.cumsum(x)]) / x.sum()
    pob = np.linspace(0, 1, x.size + 1)
    return pob, acum


def participacion_top(x, fraccion: float = 0.10) -> float:
    x = np.sort(np.asarray(x, dtype=float))[::-1]
    k = max(1, int(round(fraccion * x.size)))
    return float(x[:k].sum() / x.sum())


def entropia(p, k: int | None = None) -> tuple[float, float]:
    """Entropía de Shannon (bits) y normalizada H / log2(K)."""
    p = np.asarray(p, dtype=float)
    p = p[p > 0]
    p = p / p.sum()
    h = float(-(p * np.log2(p)).sum())
    k = k or p.size
    return h, (h / np.log2(k) if k > 1 else np.nan)
