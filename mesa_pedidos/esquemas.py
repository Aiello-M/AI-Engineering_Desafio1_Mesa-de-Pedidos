""" Modelos de Pydantic para que el LLM conteste siempre con la misma forma (structured output)
    (las description también las lee el LLM, así que funcionan como parte del prompt)
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field


# define la respuesta de clasificar: la intención, por qué la eligió y la fecha que menciona el cliente (si hay)
class Clasificacion(BaseModel):
    intencion: Literal["consulta", "pedido", "derivar"] = Field(
        description="Tipo de mensaje: consulta, pedido o derivar"
    )
    motivo: str = Field(description="Una oración que explica por qué se eligió ese tipo de mensaje")
    fecha_mencionada: Optional[str] = Field(
        description=("Fecha exacta que menciona el cliente de un presupuesto, una compra o una factura anterior, "
                     "en formato AAAA-MM-DD. Si no dice el año, usá el de la fecha del mensaje. "
                     "Si no menciona ninguna fecha o la fecha es imprecisa, poné null y no inventes un día.")
    )


# define un producto pedido (la cantidad tiene que ser mayor que 0)
class ItemPedido(BaseModel):
    sku: Optional[str] = Field(
        description="SKU del catálogo (ej. 'AB-1240'). Si no podés identificar el producto con certeza, poné null."
    )
    cantidad: int = Field(gt=0, description="Cantidad de unidades que pide el cliente (mayor que cero)")
    descripcion: str = Field(description="Nombre del producto tal como lo escribió el cliente")


# define la respuesta de extraer_pedido: los productos y las condiciones que pide el cliente
class PedidoExtraido(BaseModel):
    items: list[ItemPedido] = Field(description="Lista de productos pedidos (un item por producto)")
    descuento_solicitado: Optional[float] = Field(
        description="Porcentaje de descuento total que pide el cliente (ej. 12 para 12%). Si no pide descuento, poné null."
    )
    forma_pago: Literal["cuenta_corriente", "anticipado", "contado", "no_indicada"] = Field(
        description=("Forma de pago que pide el cliente: cuenta_corriente si pide plazo en días o 'a cuenta', "
                     "anticipado si paga antes del envío (por transferencia), contado si paga contra entrega "
                     "y no_indicada si no dice cómo paga.")
    )
    plazo_dias: Optional[int] = Field(description="Días de plazo que pide el cliente (ej. 30 o 60). Si no dice, poné null.")
    destino: Optional[str] = Field(description="Lugar de entrega que menciona el cliente. Si no dice, poné null.")