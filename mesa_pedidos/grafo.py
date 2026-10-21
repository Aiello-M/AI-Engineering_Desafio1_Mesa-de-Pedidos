""" Grafo con los 9 nodos, las aristas y los 3 routers
    (los routers solo leen la decisión que tomó el nodo anterior)
"""

from contextlib import contextmanager
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langchain_core.runnables.graph import NodeStyles
import config
from mesa_pedidos import nodos
from mesa_pedidos.estado import EstadoMesa


# router 1: después de clasificar lee la intención (consulta, pedido o derivar)
def ruta_por_intencion(state: EstadoMesa) -> str:
    return state["intencion"]


# router 2: después de validar_pedido lee la decisión (confirmar, humano, rechazar o derivar)
def ruta_por_validacion(state: EstadoMesa) -> str:
    return state["decision_validacion"]


# router 3: después de aprobacion_humana lee si el pedido se confirma (aprueba o rechaza)
def ruta_post_aprobacion(state: EstadoMesa) -> str:
    return state["decision_humana"]["ruta"]


# arma el grafo con los 9 nodos, las aristas fijas y las 3 aristas condicionales
def construir_grafo(checkpointer=None):
    builder = StateGraph(EstadoMesa)

    builder.add_node("cargar_cliente", nodos.cargar_cliente)
    builder.add_node("clasificar", nodos.clasificar)
    builder.add_node("responder_consulta", nodos.responder_consulta)
    builder.add_node("extraer_pedido", nodos.extraer_pedido)
    builder.add_node("validar_pedido", nodos.validar_pedido)
    builder.add_node("aprobacion_humana", nodos.aprobacion_humana)
    builder.add_node("confirmar_pedido", nodos.confirmar_pedido)
    builder.add_node("rechazar_pedido", nodos.rechazar_pedido)
    builder.add_node("derivar_humano", nodos.derivar_humano)

    builder.add_edge(START, "cargar_cliente")
    builder.add_edge("cargar_cliente", "clasificar")

    builder.add_conditional_edges("clasificar", ruta_por_intencion, {
        "consulta": "responder_consulta",
        "pedido": "extraer_pedido",
        "derivar": "derivar_humano",
    })
    builder.add_edge("extraer_pedido", "validar_pedido")

    builder.add_conditional_edges("validar_pedido", ruta_por_validacion, {
        "confirmar": "confirmar_pedido",
        "humano": "aprobacion_humana",
        "rechazar": "rechazar_pedido",
        "derivar": "derivar_humano",
    })
    builder.add_conditional_edges("aprobacion_humana", ruta_post_aprobacion, {
        "aprueba": "confirmar_pedido",
        "rechaza": "rechazar_pedido",
    })

    # las 4 hojas terminan el recorrido
    for hoja in ("responder_consulta", "confirmar_pedido", "rechazar_pedido", "derivar_humano"):
        builder.add_edge(hoja, END)

    return builder.compile(checkpointer=checkpointer)


# abre el grafo con el estado guardado en un archivo .sqlite
# (un pedido que espera a Gerencia se puede retomar aunque se cierre el programa)
@contextmanager
def abrir_grafo_persistente(ruta_db=config.CHECKPOINTS_DB):
    config.DIR_ARTEFACTOS.mkdir(exist_ok=True)
    with SqliteSaver.from_conn_string(str(ruta_db)) as checkpointer:
        yield construir_grafo(checkpointer)


# arma la config con el id del mensaje como thread_id (con ese id se retoma el pedido guardado)
def armar_config_hilo(id_mensaje: str) -> dict:
    return {"configurable": {"thread_id": id_mensaje}}


if __name__ == "__main__":
    # colores de las cajas con letra oscura para que se lean en GitHub con fondo claro y oscuro
    estilos = NodeStyles(
        default="fill:#fdf1e3,stroke:#d9822b,stroke-width:1.5px,color:#3b2a1a",
        first="fill:#ffffff,stroke:#d9822b,color:#3b2a1a",
        last="fill:#f4b26b,stroke:#b8641a,color:#3b2a1a",
    )
    # imprime el diagrama del grafo (en Mermaid)
    print(construir_grafo().get_graph().draw_mermaid(node_colors=estilos))