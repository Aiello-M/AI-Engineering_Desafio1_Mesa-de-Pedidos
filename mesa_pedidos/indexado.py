""" Parte los 4 PDF de políticas en chunks (uno por artículo o por producto) y arma el índice FAISS.
    Se corre una vez con python indexar.py y el índice queda guardado en artefactos.
"""

import json
import re
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
import config


# lee los PDF y devuelve un Document por página: el texto de la página
# con el nombre del PDF y el número de página (para poder citar la fuente)
def cargar_paginas() -> list[Document]:
    paginas = []
    for pdf in sorted(config.DIR_POLITICAS.glob("*.pdf")):
        for pagina in PyPDFLoader(str(pdf)).load():
            pagina.metadata = {"documento": pdf.name, "pagina": pagina.metadata.get("page", 0) + 1}
            paginas.append(pagina)
    return paginas


# patrón del inicio de una sección ("ART. 4 - ...", "2. DEVOLUCION POR ..." o una ficha "HE-4330 - ...")
INICIO_SECCION = re.compile(r"^(ART\. \d+ - |\d+\. [A-Z][A-Z ,]+$|[A-Z]{2}-\d{4} - )")
# patrón de los títulos de rubro de las fichas (ej. "HERRAMIENTA ELECTRICA"): todo en mayúsculas y sin números
TITULO_RUBRO = re.compile(r"^[A-Z][A-Z ,]+$")
# patrón del pie de página que se repite en todas las páginas (se saca antes de partir)
PIE_PAGINA = re.compile(r"Documento interno de uso comercial\..*?Gerencia\s*Comercial\.", re.S)


# parte los PDF en un chunk por artículo (en las fichas, uno por producto)
# (no se usa tamaño fijo porque la regla de devolución de 15 días y la excepción de los zapatos de seguridad quedarían separadas)
def partir_en_chunks(paginas: list[Document]) -> list[Document]:
    chunks = []
    paginas_por_pdf = {}
    for pagina in paginas:
        documento = pagina.metadata["documento"]
        if documento not in paginas_por_pdf:
            paginas_por_pdf[documento] = []
        paginas_por_pdf[documento].append(pagina)

    for documento, paginas_pdf in paginas_por_pdf.items():
        # junta las líneas de todas las páginas (para que no se corte un artículo que sigue en la pg siguiente)
        lineas = []
        for pagina in paginas_pdf:
            texto = PIE_PAGINA.sub("", pagina.page_content)
            lineas += [(linea.strip(), pagina.metadata["pagina"]) for linea in texto.splitlines() if linea.strip()]

        # la 2da línea de cada PDF es el título
        if len(lineas) > 1:
            titulo = lineas[1][0]
        else:
            titulo = documento

        rubro = ""
        secciones = []
        for texto, numero_pagina in lineas[2:]:
            if INICIO_SECCION.match(texto):
                secciones.append({"pagina_inicio": numero_pagina, "pagina_fin": numero_pagina, "rubro": rubro, "lineas": [texto]})
            elif TITULO_RUBRO.match(texto) and documento.startswith("fichas"):
                rubro = texto
            elif secciones:
                secciones[-1]["pagina_fin"] = numero_pagina
                secciones[-1]["lineas"].append(texto)

        for seccion in secciones:
            # agrega adelante el título del PDF (y el rubro en las fichas) para que se sepa de qué documento es cada chunk
            if seccion["rubro"]:
                encabezado = f"[{titulo} - {seccion['rubro']}]"
            else:
                encabezado = f"[{titulo}]"
            contenido = encabezado + "\n" + "\n".join(seccion["lineas"])
            chunks.append(Document(page_content=contenido, metadata={
                "documento": documento, "pagina": seccion["pagina_inicio"], "pagina_fin": seccion["pagina_fin"]}))

    # si algún artículo supera el máximo de 1500 caracteres: se corta en partes más chicas
    splitter = RecursiveCharacterTextSplitter(chunk_size=config.CHUNK_MAX, chunk_overlap=100)
    return splitter.split_documents(chunks)


# crea el modelo de embeddings de OpenAI
def crear_embeddings():
    config.revisar_api_key()
    return OpenAIEmbeddings(model=config.MODELO_EMBEDDINGS)


# guarda el texto de los chunks para que BM25 pueda buscar por palabras
def guardar_chunks(chunks: list[Document]) -> None:
    config.DIR_ARTEFACTOS.mkdir(exist_ok=True)
    datos = [{"texto": chunk.page_content, "metadata": chunk.metadata} for chunk in chunks]
    config.CHUNKS_JSON.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")


# lee los chunks del json (o los arma desde los PDF si el json todavía no existe)
def cargar_chunks() -> list[Document]:
    if not config.CHUNKS_JSON.exists():
        guardar_chunks(partir_en_chunks(cargar_paginas()))
    datos = json.loads(config.CHUNKS_JSON.read_text(encoding="utf-8"))
    return [Document(page_content=chunk["texto"], metadata=chunk["metadata"]) for chunk in datos]


# crea el índice FAISS con los embeddings de los chunks y lo guarda
def indexar(forzar: bool = False):
    # si el índice ya existe, lo carga de disco para no pagar los embeddings otra vez
    if config.DIR_INDICE.exists() and not forzar:
        # FAISS pide allow_dangerous_deserialization para abrir el índice guardado (no hay riesgo: lo creó este programa)
        return FAISS.load_local(str(config.DIR_INDICE), crear_embeddings(), allow_dangerous_deserialization=True)

    chunks = partir_en_chunks(cargar_paginas())
    guardar_chunks(chunks)
    vectorstore = FAISS.from_documents(chunks, crear_embeddings())
    vectorstore.save_local(str(config.DIR_INDICE))
    print(f"Listo: {len(chunks)} chunks indexados en {config.DIR_INDICE}")
    return vectorstore