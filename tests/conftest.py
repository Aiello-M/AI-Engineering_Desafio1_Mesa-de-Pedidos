""" Prepara los tests para que corran sin API key
    (cambia las llamadas al LLM por las respuestas del golden set y la búsqueda con embeddings por BM25)
"""

import json
import pytest
from langchain_community.retrievers import BM25Retriever
import config
from mesa_pedidos import indexado, llm, retriever
from mesa_pedidos.esquemas import Clasificacion, ItemPedido, PedidoExtraido

GOLDEN = {caso["id"]: caso for caso in json.loads(config.GOLDEN_SET.read_text(encoding="utf-8"))["casos"]}
MENSAJES = [json.loads(linea) for linea in config.BANDEJA.read_text(encoding="utf-8").splitlines() if linea.strip()]
BANDEJA = {mensaje["id"]: mensaje for mensaje in MENSAJES}

# busca el caso del golden set por el texto (las funciones del LLM reciben el texto y no el id)
GOLDEN_POR_TEXTO = {mensaje["texto"]: GOLDEN[mensaje["id"]] for mensaje in MENSAJES}

# forma de pago, plazo y descuento que pide cada mensaje (el golden set solo trae los productos)
CONDICIONES_PEDIDO = {
    "MSG-010": {"forma_pago": "cuenta_corriente"},
    "MSG-011": {"forma_pago": "anticipado"},
    "MSG-013": {"forma_pago": "cuenta_corriente", "plazo_dias": 45},
    "MSG-014": {"forma_pago": "cuenta_corriente", "plazo_dias": 30},
    "MSG-015": {"forma_pago": "cuenta_corriente", "plazo_dias": 30},
    "MSG-016": {"descuento_solicitado": 25.0},
    "MSG-017": {"forma_pago": "cuenta_corriente", "plazo_dias": 30},
}

# fecha que menciona el cliente en el MSG-005 (es la única de la bandeja)
FECHAS_MENCIONADAS = {"MSG-005": "2026-09-10"}


# devuelve la intención del golden set como si la hubiera elegido el LLM
def simular_clasificacion(texto, fecha):
    caso = GOLDEN_POR_TEXTO[texto]
    return Clasificacion(intencion=caso["intencion"], motivo="respuesta simulada",
                         fecha_mencionada=FECHAS_MENCIONADAS.get(caso["id"]))


# devuelve los productos del golden set con las condiciones de cada pedido
def simular_extraccion(texto):
    caso = GOLDEN_POR_TEXTO[texto]
    condiciones = CONDICIONES_PEDIDO.get(caso["id"], {})
    items = [ItemPedido(sku=item["sku"], cantidad=item["cantidad"], descripcion=item["sku"]) for item in caso["items"]]
    return PedidoExtraido(
        items=items,
        descuento_solicitado=condiciones.get("descuento_solicitado"),
        forma_pago=condiciones.get("forma_pago", "no_indicada"),
        plazo_dias=condiciones.get("plazo_dias"),
        destino=None,
    )


# devuelve lo que recibió el LLM (así los tests pueden revisar qué le llegó)
def simular_respuesta(pregunta, contexto, cliente, fecha, calculo_dias):
    return f"RESPUESTA SIMULADA\nfecha: {fecha}\ncálculo de días: {calculo_dias}\n{contexto}"


# reemplaza el índice FAISS por BM25 (los embeddings necesitan la API key)
class IndiceSimulado:
    def as_retriever(self, search_kwargs):
        buscador = BM25Retriever.from_documents(indexado.cargar_chunks(), preprocess_func=retriever.tokenizar)
        buscador.k = search_kwargs["k"]
        return buscador


def simular_indice():
    return IndiceSimulado()


# cambia las funciones del LLM y el índice por las simuladas (al terminar c/test vuelven las funciones originales)
@pytest.fixture
def llm_simulado(monkeypatch):
    monkeypatch.setattr(llm, "clasificar_mensaje", simular_clasificacion)
    monkeypatch.setattr(llm, "extraer_pedido", simular_extraccion)
    monkeypatch.setattr(llm, "responder_consulta", simular_respuesta)
    monkeypatch.setattr(retriever, "cargar_indice", simular_indice)