""" Estado del grafo (campos que se pasan los nodos) """ 

from operator import add
from typing import Annotated, Optional, TypedDict

# estado del grafo (total=False porque cada nodo va agregando sus campos)
class EstadoMesa(TypedDict, total=False):
    # entrada (cargada por correr.py)
    id_mensaje: str
    cuit: str
    texto: str
    fecha: str  # fecha del msj (viene en la bandeja)

    # lo que va completando cada nodo
    cliente: Optional[dict] # cargar_cliente (None si CUIT no existe)
    intencion: str  # clasificar
    motivo_clasificacion: str    # clasificar
    fecha_mencionada: Optional[str]  # clasificar
    pedido: dict   # extraer_pedido
    validacion: dict   # validar_pedido
    decision_validacion: str # validar_pedido 
    decision_humana: dict  # aprobacion_humana
    validacion_final: dict  # aprobacion_humana (el pedido recalculado con el stock que hay)
    pendientes: list[dict]  # aprobacion_humana (lo que queda sin entregar)
    confirmacion: dict  # confirmar_pedido 
    respuesta: str  # la escribe el nodo donde termina
    fuentes: list[dict]  # responder_consulta
    nodo_final: str  # nodo donde terminó (lo usa evaluar.py)

    # cada nodo suma su línea al log sin pisarse
    log: Annotated[list[str], add]