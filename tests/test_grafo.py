""" Prueba el grafo completo con el LLM simulado: rutas, citas, fechas, aprobación de Gerencia y checkpointer """

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from mesa_pedidos.grafo import abrir_grafo_persistente, armar_config_hilo, construir_grafo
from tests.conftest import BANDEJA, GOLDEN


# corre un msj de la bandeja y devuelve la config del hilo para leer el estado después
def correr_mensaje(grafo, id_mensaje):
    mensaje = BANDEJA[id_mensaje]
    config_hilo = armar_config_hilo(id_mensaje)
    grafo.invoke({"id_mensaje": id_mensaje, "cuit": mensaje["cuit"], "texto": mensaje["texto"],
                  "fecha": mensaje["fecha"], "log": []}, config_hilo)
    return config_hilo


# con el LLM simulado c/mensaje tiene que ir por la ruta del golden set
def test_cada_mensaje_va_por_su_ruta(llm_simulado):
    grafo = construir_grafo(InMemorySaver())
    for id_mensaje in BANDEJA:
        estado = grafo.get_state(correr_mensaje(grafo, id_mensaje))
        if estado.next:
            ruta = estado.next[0]
        else:
            ruta = estado.values["nodo_final"]
        assert ruta == GOLDEN[id_mensaje]["ruta"], id_mensaje


# c/nodo suma su línea al log (si falta el reducer queda solo la última)
def test_cada_nodo_suma_su_linea_al_log(llm_simulado):
    grafo = construir_grafo(InMemorySaver())
    valores = grafo.get_state(correr_mensaje(grafo, "MSG-009")).values
    assert len(valores["log"]) == 5


def test_la_consulta_trae_la_ficha_del_producto(llm_simulado):
    grafo = construir_grafo(InMemorySaver())
    valores = grafo.get_state(correr_mensaje(grafo, "MSG-004")).values
    documentos = [fuente["documento"] for fuente in valores["fuentes"]]
    assert "fichas_tecnicas_2026.pdf" in documentos


def test_al_llm_le_llega_el_calculo_del_presupuesto(llm_simulado):
    grafo = construir_grafo(InMemorySaver())
    valores = grafo.get_state(correr_mensaje(grafo, "MSG-005")).values
    assert "venció el 2026-09-17" in valores["respuesta"]


def test_la_confirmacion_muestra_los_montos_en_pesos(llm_simulado):
    grafo = construir_grafo(InMemorySaver())
    valores = grafo.get_state(correr_mensaje(grafo, "MSG-009")).values
    assert "Neto: $927.940,00" in valores["respuesta"]


def test_el_pedido_frenado_trae_los_datos_para_gerencia(llm_simulado):
    grafo = construir_grafo(InMemorySaver())
    payload = grafo.get_state(correr_mensaje(grafo, "MSG-016")).tasks[0].interrupts[0].value
    for campo in ("razon_social", "credito_disponible", "monto_con_descuento", "motivos_aprobacion", "productos"):
        assert campo in payload


# piden 60 HE-4110 y hay 52: si Gerencia aprueba se mandan 52 y quedan 8 pendientes
def test_si_gerencia_aprueba_se_manda_lo_que_hay_en_stock(llm_simulado):
    grafo = construir_grafo(InMemorySaver())
    config_hilo = correr_mensaje(grafo, "MSG-016")
    grafo.invoke(Command(resume={"accion": "aprobar", "comentario": "ok"}), config_hilo)
    valores = grafo.get_state(config_hilo).values
    assert valores["nodo_final"] == "confirmar_pedido"
    assert valores["confirmacion"]["pendientes"][0]["cantidad"] == 8


# Gerencia autoriza 22%, pero la marca Dewalt sigue con el tope de 15%
def test_gerencia_autoriza_otro_descuento(llm_simulado):
    grafo = construir_grafo(InMemorySaver())
    config_hilo = correr_mensaje(grafo, "MSG-016")
    grafo.invoke(Command(resume={"accion": "aprobar", "comentario": "ok", "descuento_autorizado": 22}), config_hilo)
    valores = grafo.get_state(config_hilo).values
    descuentos = {}
    for producto in valores["confirmacion"]["productos"]:
        descuentos[producto["sku"]] = producto["descuento_aplicado"]
    assert descuentos["AB-1035"] == 22
    assert descuentos["HE-4110"] == 15


def test_si_gerencia_rechaza_el_pedido_se_rechaza(llm_simulado):
    grafo = construir_grafo(InMemorySaver())
    config_hilo = correr_mensaje(grafo, "MSG-013")
    grafo.invoke(Command(resume={"accion": "rechazar", "comentario": "no"}), config_hilo)
    assert grafo.get_state(config_hilo).values["nodo_final"] == "rechazar_pedido"


# simula cerrar el programa mientras el pedido espera a Gerencia y retomarlo con un grafo nuevo
def test_cortar_y_retomar_el_pedido(llm_simulado, tmp_path):
    ruta_db = tmp_path / "checkpoints.sqlite"
    with abrir_grafo_persistente(ruta_db) as grafo:
        config_hilo = correr_mensaje(grafo, "MSG-013")
        assert grafo.get_state(config_hilo).next == ("aprobacion_humana",)
    with abrir_grafo_persistente(ruta_db) as grafo_nuevo:
        grafo_nuevo.invoke(Command(resume={"accion": "aprobar", "comentario": "ok"}), config_hilo)
        assert grafo_nuevo.get_state(config_hilo).values["nodo_final"] == "confirmar_pedido"