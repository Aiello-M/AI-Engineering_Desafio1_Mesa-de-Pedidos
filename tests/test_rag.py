""" Prueba cómo se parten los PDF en chunks y la búsqueda con BM25 (sin API key) """

from langchain_text_splitters import RecursiveCharacterTextSplitter
from mesa_pedidos.indexado import cargar_paginas, partir_en_chunks
from mesa_pedidos.retriever import armar_bm25, tokenizar

CHUNKS = partir_en_chunks(cargar_paginas())


def test_cantidad_de_chunks():
    assert len(CHUNKS) == 59


def test_la_regla_de_devolucion_queda_junto_con_su_excepcion():
    chunks_arrepentimiento = [chunk for chunk in CHUNKS if "DEVOLUCION POR ARREPENTIMIENTO" in chunk.page_content]
    assert len(chunks_arrepentimiento) == 1
    assert "zapatos de seguridad" in chunks_arrepentimiento[0].page_content


# muestra por qué se parte por artículo: con tamaño fijo la regla y la excepción quedan separadas
def test_con_tamano_fijo_la_excepcion_queda_separada():
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
    chunks_tamano_fijo = splitter.split_documents(cargar_paginas())
    chunks_con_regla = [chunk for chunk in chunks_tamano_fijo if "Se acepta devolucion" in chunk.page_content]
    assert "zapatos de seguridad" not in chunks_con_regla[0].page_content


def test_el_pie_de_pagina_no_se_indexa():
    for chunk in CHUNKS:
        assert "Documento interno de uso comercial" not in chunk.page_content


def test_tokenizar_deja_el_sku_como_una_palabra():
    assert tokenizar("SKU HE-4330?") == ["sku", "he-4330"]


# BM25 busca el código exacto (para los embeddings el HE-4330, el HE-4335 y el HE-4410 se parecen)
def test_bm25_trae_primero_la_ficha_del_sku():
    retriever_bm25 = armar_bm25()
    primer_chunk = retriever_bm25.invoke("el atornillador SKU HE-4330 viene con bateria?")[0]
    assert "HE-4330 - " in primer_chunk.page_content