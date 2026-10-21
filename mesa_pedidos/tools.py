""" Las 2 tools: consultar_producto y verificar_credito
    (las llama el nodo validar_pedido en todos los pedidos)
"""

from decimal import Decimal
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from mesa_pedidos.datos import leer_catalogo, leer_clientes, normalizar_cuit, normalizar_sku


# convierte un Decimal a texto con 2 decimales (ej. "1550000.00")
def convertir_a_texto(valor: Decimal) -> str:
    return str(valor.quantize(Decimal("0.01")))


# define qué datos recibe consultar_producto (la cantidad tiene que ser mayor a 0)
class ConsultarProductoInput(BaseModel):
    sku: str = Field(description="Código del producto (ej. 'AB-1240')")
    cantidad: int = Field(default=1, ge=1, description="Unidades pedidas, para ver si alcanza el stock")


# define qué datos recibe verificar_credito (el monto no puede ser negativo)
class VerificarCreditoInput(BaseModel):
    cuit: str = Field(description="CUIT del cliente, con o sin guiones")
    monto_pedido: Decimal = Field(ge=0, description="Monto del pedido nuevo con descuento, sin IVA, en pesos")


# tool 1: busca un producto en el catálogo y revisa si alcanza el stock
@tool(args_schema=ConsultarProductoInput)
def consultar_producto(sku: str, cantidad: int = 1) -> dict:
    """Busca un producto por SKU en el catálogo y devuelve nombre, marca, rubro,
    precio de lista sin IVA, stock, depósito y si alcanza el stock para la cantidad pedida."""
    producto = leer_catalogo().get(normalizar_sku(sku))
    if producto is None:
        # si el SKU no existe devuelve el error como dato (así el nodo puede derivar el pedido en vez de cortarse)
        return {"encontrado": False, "sku": sku, "error": f"El SKU {sku} no existe en el catálogo"}
    return {
        "encontrado": True,
        "sku": producto["sku"],
        "nombre": producto["nombre"],
        "marca": producto["marca"],
        "rubro": producto["rubro"],
        "precio_lista": float(producto["precio_lista"]),
        "alicuota_iva": float(producto["alicuota_iva"]),
        "stock": int(producto["stock"]),
        "deposito": producto["deposito"],
        "cantidad_pedida": cantidad,
        "stock_suficiente": int(producto["stock"]) >= cantidad,
    }


# tool 2: calcula si el pedido nuevo entra en el crédito del cliente y trae su mora y estado
@tool(args_schema=VerificarCreditoInput)
def verificar_credito(cuit: str, monto_pedido: Decimal) -> dict:
    """Devuelve la situación de crédito de un cliente para un pedido nuevo: límite, saldo,
    crédito disponible, si el pedido entra en el límite (saldo + monto del pedido <= límite), mora y estado."""
    cliente = leer_clientes().get(normalizar_cuit(cuit))
    if cliente is None:
        return {"encontrado": False, "cuit": cuit, "error": "El CUIT no pertenece a ningún cliente registrado"}

    # pasa los montos a Decimal
    limite = Decimal(str(cliente["limite_credito"]))
    saldo = Decimal(str(cliente["saldo_actual"]))
    monto_pedido = Decimal(str(monto_pedido))

    # devuelve los montos como texto (para guardar en json sin perder precisión)
    return {
        "encontrado": True,
        "cuit": cliente["cuit"],
        "razon_social": cliente["razon_social"],
        "limite_credito": convertir_a_texto(limite),
        "saldo_actual": convertir_a_texto(saldo),
        "credito_disponible": convertir_a_texto(limite - saldo),
        "monto_pedido": convertir_a_texto(monto_pedido),
        "saldo_despues": convertir_a_texto(saldo + monto_pedido),
        "entra_en_limite": saldo + monto_pedido <= limite,
        "mora_dias": int(cliente["mora_dias"]),
        "estado": cliente["estado"],
    }