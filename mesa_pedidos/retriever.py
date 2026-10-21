""" Búsqueda híbrida en los PDF: embeddings (FAISS) + BM25, unidos con EnsembleRetriever.
    (BM25 busca el código exacto, los embeddings confunden códigos parecidos)
"""

import re
import unicodedata
from functools import lru_cache
from langchain_classic.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
import config
from mesa_pedidos import indexado


# pasa el texto a minúsculas, le saca las tildes y lo separa en palabras para BM25
# (deja "he-4330" como una sola palabra para que BM25 busque el código completo)
def tokenizar(texto: str) -> list[str]:
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+(?:[-.][a-z0-9]+)*", texto)


# arma el buscador BM25 con los chunks del json (lru_cache guarda el resultado para armarlo una sola vez)
@lru_cache(maxsize=1)
def armar_bm25() -> BM25Retriever:
    return BM25Retriever.from_documents(indexado.cargar_chunks(), preprocess_func=tokenizar)


# carga el índice FAISS de disco (también una sola vez)
@lru_cache(maxsize=1)
def cargar_indice():
    return indexado.indexar()


# devuelve los chunks que más se parecen a la consulta (con búsqueda híbrida o solo con embeddings)
def recuperar(consulta: str, k: int = config.K_RECUPERAR, hibrido: bool | None = None) -> list[Document]:
    if hibrido is None:
        hibrido = config.USAR_HIBRIDO   # se lee en cada búsqueda porque evaluar.py lo puede cambiar

    # cada búsqueda trae 12 chunks y al final quedan los 4 mejores
    retriever_densa = cargar_indice().as_retriever(search_kwargs={"k": k * 3})
    if not hibrido:
        return retriever_densa.invoke(consulta)[:k]

    retriever_bm25 = armar_bm25()
    retriever_bm25.k = k * 3
    # las dos búsquedas pesan lo mismo (si BM25 pesa menos, se puede perder el SKU exacto)
    retriever_hibrido = EnsembleRetriever(retrievers=[retriever_bm25, retriever_densa], weights=[0.5, 0.5])
    return retriever_hibrido.invoke(consulta)[:k]


# arma el texto que recibe el LLM: cada chunk con su fuente adelante, para que la copie al citar
def formatear_contexto(chunks: list[Document]) -> str:
    return "\n\n".join(f"[{chunk.metadata['documento']}, p. {obtener_paginas(chunk)}]\n{chunk.page_content}" for chunk in chunks)


# devuelve la página del chunk para la cita; si el artículo sigue en la siguiente, devuelve "1-2"
def obtener_paginas(chunk: Document) -> str:
    pagina_inicio = chunk.metadata["pagina"]
    pagina_fin = chunk.metadata.get("pagina_fin", pagina_inicio)
    if pagina_inicio == pagina_fin:
        return str(pagina_inicio)
    else:
        return f"{pagina_inicio}-{pagina_fin}"