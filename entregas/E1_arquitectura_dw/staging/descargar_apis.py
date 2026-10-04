"""
Descarga las fuentes API del catálogo de E1 a archivos listos para cargar
en la capa staging de BigQuery. Solo usa la biblioteca estándar de Python.

    python3 descargar_apis.py

Genera, en esta misma carpeta:
  - festivos_mx_nager_2010_2026.jsonl   (F4, Nager.Date)
  - clima_cdmx_openmeteo_2010_2026.csv  (F5, Open-Meteo Historical Weather)

No se transforma el contenido. La única operación sobre F4 es de formato:
la API devuelve un arreglo JSON por año y BigQuery requiere JSON delimitado
por saltos de línea (un objeto por línea). Ninguna fuente requiere llave.
"""

import json
import pathlib
import urllib.request
from datetime import date

AQUI = pathlib.Path(__file__).resolve().parent
ANIOS = range(2010, 2027)
FECHA_FIN = "2026-07-31"  # último día publicado en F1 al 2026-10-01


def obtener(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read()


def festivos() -> None:
    destino = AQUI / "festivos_mx_nager_2010_2026.jsonl"
    filas = 0
    with destino.open("w", encoding="utf-8") as out:
        for anio in ANIOS:
            url = f"https://date.nager.at/api/v3/PublicHolidays/{anio}/MX"
            for registro in json.loads(obtener(url)):
                out.write(json.dumps(registro, ensure_ascii=False) + "\n")
                filas += 1
    print(f"F4 festivos: {filas} registros -> {destino.name}")


def clima() -> None:
    destino = AQUI / "clima_cdmx_openmeteo_2010_2026.csv"
    url = (
        "https://archive-api.open-meteo.com/v1/archive"
        "?latitude=19.4326&longitude=-99.1332"
        f"&start_date=2010-01-01&end_date={FECHA_FIN}"
        "&daily=precipitation_sum,rain_sum,temperature_2m_max,temperature_2m_min"
        "&timezone=America%2FMexico_City&format=csv"
    )
    destino.write_bytes(obtener(url))
    lineas = destino.read_text(encoding="utf-8").strip().splitlines()
    print(f"F5 clima: {len(lineas) - 4} días -> {destino.name} "
          "(las primeras 4 líneas son metadatos: usar 'filas a omitir = 4')")


if __name__ == "__main__":
    print(f"Descarga del {date.today().isoformat()}")
    festivos()
    clima()
