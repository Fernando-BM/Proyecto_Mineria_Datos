"""Estilo común de las figuras: legible en pantalla y en escala de grises."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

# Paleta de 6 tonos con luminosidad distinta (se distinguen en gris).
TINTA = "#1C2033"
GRIS = "#8A8F9C"
COLORES = ["#1F3A93", "#E8781E", "#2E9565", "#8457B8", "#C0392B", "#B8921C"]

plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 150, "font.size": 10, "axes.titlesize": 11.5,
    "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.labelsize": 10,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.color": "#E6E8ED", "grid.linewidth": 0.6, "axes.edgecolor": "#9AA0AC",
    "axes.labelcolor": TINTA, "xtick.color": TINTA, "ytick.color": TINTA,
    "legend.frameon": False, "figure.facecolor": "white",
})

miles = FuncFormatter(lambda x, _: f"{x:,.0f}")
millones = FuncFormatter(lambda x, _: f"{x / 1e6:,.1f}")
pct = FuncFormatter(lambda x, _: f"{x:.0%}")


def figura(ancho: float = 9, alto: float = 4.2, **kw):
    return plt.subplots(figsize=(ancho, alto), **kw)


def fuente(ax, texto: str) -> None:
    ax.annotate(texto, xy=(0, -0.16), xycoords="axes fraction", fontsize=7.5, color=GRIS, va="top")
