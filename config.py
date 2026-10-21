""" Rutas, modelos y parámetros del proyecto """

import os
from pathlib import Path
from dotenv import load_dotenv

# lee la API key del archivo .env
load_dotenv()
RAIZ = Path(__file__).resolve().parent

# datos del desafío
DIR_DATOS = RAIZ / "datos"
DIR_POLITICAS = DIR_DATOS / "politicas"
CSV_CATALOGO = DIR_DATOS / "catalogo.csv"
CSV_CLIENTES = DIR_DATOS / "clientes.csv"
BANDEJA = DIR_DATOS / "bandeja.jsonl"
GOLDEN_SET = DIR_DATOS / "golden_set.json"

# archivos que genera el programa
DIR_ARTEFACTOS = RAIZ / "artefactos"
DIR_INDICE = DIR_ARTEFACTOS / "indice_faiss"
CHUNKS_JSON = DIR_ARTEFACTOS / "chunks.json"
CHECKPOINTS_DB = DIR_ARTEFACTOS / "checkpoints.sqlite"
EVALUACION_JSON = RAIZ / "evaluacion.json"

# modelos
MODELO_LLM = os.getenv("MODELO_LLM", "gpt-4o-mini")
MODELO_EMBEDDINGS = os.getenv("MODELO_EMBEDDINGS", "text-embedding-3-small")

# tamaño máximo de un chunk (por si un artículo es muy largo)
CHUNK_MAX = 1500
# cant de chunks que devuelve c/búsqueda
K_RECUPERAR = 4
# búsqueda híbrida por defecto (con 0 usa solo embeddings)
USAR_HIBRIDO = os.getenv("USAR_HIBRIDO", "1") == "1"


# verifica que haya API key (si no hay muestra un msj indicando qué hacer)
def revisar_api_key() -> None:
    clave = os.getenv("OPENAI_API_KEY")
    if not clave:
        raise SystemExit("Falta la API key: copiá .env.example como .env y completá OPENAI_API_KEY.")