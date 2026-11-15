"""Conexión a BigQuery sin llaves en el repositorio.

Orden de autenticación:
  1. Credenciales de aplicación por defecto (ADC), p. ej. después de
     `gcloud auth application-default login`.
  2. En Google Colab: `google.colab.auth.authenticate_user()`.
  3. En una computadora sin gcloud: inicio de sesión en el navegador con
     pydata-google-auth (la credencial queda en ~/.pydata_google_auth,
     fuera del repositorio).
"""

from __future__ import annotations

from .utiles import LOG

ALCANCES = ["https://www.googleapis.com/auth/bigquery",
            "https://www.googleapis.com/auth/cloud-platform"]


def _credenciales():
    import google.auth
    try:
        cred, _ = google.auth.default(scopes=ALCANCES)
        LOG.info("Autenticación: credenciales de aplicación por defecto (ADC)")
        return cred
    except Exception:  # noqa: BLE001 - se intenta el siguiente método
        pass
    try:
        from google.colab import auth as colab_auth  # type: ignore
        colab_auth.authenticate_user()
        cred, _ = google.auth.default(scopes=ALCANCES)
        LOG.info("Autenticación: Google Colab")
        return cred
    except ImportError:
        pass
    import pydata_google_auth
    LOG.info("Autenticación: inicio de sesión en el navegador (pydata-google-auth)")
    return pydata_google_auth.get_user_credentials(ALCANCES, auth_local_webserver=True)


def cliente(cfg: dict):
    from google.cloud import bigquery
    proyecto = cfg["bigquery"]["proyecto"]
    cli = bigquery.Client(project=proyecto, credentials=_credenciales(),
                          location=cfg["bigquery"]["ubicacion"])
    LOG.info("Proyecto de BigQuery: %s", proyecto)
    return cli


def ejecutar_script(cli, sql: str, etiqueta: str) -> None:
    """Ejecuta un script SQL de varias sentencias y espera a que termine."""
    trabajo = cli.query(sql)
    trabajo.result()
    LOG.info("  SQL %s: OK (trabajo %s)", etiqueta, trabajo.job_id)


def consulta_df(cli, sql: str):
    return cli.query(sql).result().to_dataframe(create_bqstorage_client=False)


def dividir_sentencias(sql: str) -> list[str]:
    """Separa un archivo .sql en sentencias por ';' al final de línea,
    ignorando comentarios de línea completa."""
    sentencias, actual = [], []
    for linea in sql.splitlines():
        if linea.strip().startswith("--") and not actual:
            continue
        actual.append(linea)
        if linea.rstrip().endswith(";"):
            texto = "\n".join(actual).strip()
            if texto and not all(l.strip().startswith("--") or not l.strip()
                                 for l in texto.splitlines()):
                sentencias.append(texto)
            actual = []
    resto = "\n".join(actual).strip()
    if resto and not all(l.strip().startswith("--") or not l.strip() for l in resto.splitlines()):
        sentencias.append(resto)
    return sentencias
