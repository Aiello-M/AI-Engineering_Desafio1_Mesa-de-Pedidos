""" Reglas comerciales del pedido: descuentos, topes, pedido mínimo, crédito, mora e impuestos (sin LLM) """

import json
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from mesa_pedidos.tools import consultar_producto, verificar_credito

CENTAVOS = Decimal("0.01")


# lee las reglas comerciales del json (lru_cache guarda el resultado para leer el archivo 1 sola vez)
@lru_cache(maxsize=1)
def leer_reglas() -> dict:
    ruta = Path(__file__).with_name("reglas_comerciales.json")
    return json.loads(ruta.read_text(encoding="utf-8"))


# convierte los números a Decimal (pasando por str para no arrastrar el error del float)
def convertir_a_decimal(valor) -> Decimal:
    return Decimal(str(valor))


# redondea un monto a centavos (con 2 decimales, la mitad para arriba)
def redondear_monto(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


# escribe un monto con punto para los miles y coma para los decimales (ej. $7.450.000)
def formatear_monto(monto, decimales=0) -> str:
    texto = f"{monto:,.{decimales}f}"
    texto = texto.replace(",", " ")
    texto = texto.replace(".", ",")
    texto = texto.replace(" ", ".")
    return "$" + texto


# revisa el descuento que carga Gerencia (número entre 0 y menos de 100)
def validar_descuento(valor) -> Decimal | None:
    if valor is None:
        return None
    try:
        descuento = convertir_a_decimal(valor)
    except Exception:
        raise ValueError(f"El descuento '{valor}' no es un número")

    # se descarta NaN e Infinity (ya que Decimal los acepta como números)
    if not descuento.is_finite() or not (0 <= descuento < 100):
        raise ValueError(f"El descuento tiene que ser de 0 a menos de 100 (se ingresó {valor})")
    return descuento


# suma días hábiles a una fecha (cuenta de lunes a viernes desde el día siguiente, sin considerar feriados)
def sumar_dias_habiles(fecha_inicio: date, dias: int) -> date:
    fecha = fecha_inicio
    while dias > 0:
        fecha += timedelta(days=1)
        if fecha.weekday() < 5:   # weekday() da 0 el lunes y 4 el viernes
            dias -= 1
    return fecha


# cuenta los días hábiles que hay entre dos fechas
def contar_dias_habiles(fecha_inicio: date, fecha_fin: date) -> int:
    cantidad = 0
    fecha = fecha_inicio
    while fecha < fecha_fin:
        fecha += timedelta(days=1)
        if fecha.weekday() < 5:
            cantidad += 1
    return cantidad


# si el cliente menciona una fecha calcula los días que pasaron (así el LLM no tiene que contar)
# si falta alguna de las dos fechas o no se pueden leer: devuelve un texto vacío
def calcular_dias(fecha_mencionada: str | None, fecha_mensaje: str | None) -> str:
    try:
        fecha_mencionada = date.fromisoformat(fecha_mencionada)
        fecha_mensaje = date.fromisoformat(fecha_mensaje)
    except (TypeError, ValueError):
        return ""

    # si la fecha mencionada es posterior a la del mensaje: no puede ser de un presupuesto ya hecho
    if fecha_mencionada > fecha_mensaje:
        return (f"Fecha que menciona el cliente: {fecha_mencionada.isoformat()}. "
                f"Fecha del mensaje: {fecha_mensaje.isoformat()}. "
                "La fecha mencionada es posterior a la del mensaje: no se puede calcular cuánto tiempo pasó.")

    dias_corridos = (fecha_mensaje - fecha_mencionada).days
    dias_habiles = contar_dias_habiles(fecha_mencionada, fecha_mensaje)

    # la fecha puede no ser de un presupuesto: el texto da la vigencia igual y el LLM decide si la usa
    dias_vigencia = leer_reglas()["vigencia_presupuesto"]["dias_habiles"]
    fecha_vencimiento = sumar_dias_habiles(fecha_mencionada, dias_vigencia)
    if fecha_mensaje > fecha_vencimiento:
        vencimiento = f"venció el {fecha_vencimiento.isoformat()}"
    else:
        vencimiento = f"vence el {fecha_vencimiento.isoformat()} y sigue vigente"

    return (f"Fecha que menciona el cliente: {fecha_mencionada.isoformat()}. "
            f"Fecha del mensaje: {fecha_mensaje.isoformat()}. "
            f"Pasaron {dias_corridos} días corridos y {dias_habiles} días hábiles (de lunes a viernes, sin contar feriados). "
            f"Si es la fecha de un presupuesto vale {dias_vigencia} días hábiles (art. 2): {vencimiento}.")


# calcula el % de descuento por volumen según el monto de lista del pedido (art. 4)
# recorre los rangos de mayor a menor y devuelve el descuento del primero que alcanza el pedido
# (ej. 2,5 millones no llega a 6 ni a 3 pero sí a 1: 5%)
def calcular_descuento_volumen(monto_lista: Decimal) -> Decimal:
    for rango in leer_reglas()["descuento_volumen"]["rangos_monto_lista"]:
        if monto_lista >= convertir_a_decimal(rango["monto_minimo"]):
            return convertir_a_decimal(rango["descuento"])
    return Decimal(0)


# devuelve el tope de descuento de un producto (art. 5)
# 15% si es herramienta eléctrica de Dewalt, Makita o Bosch y 20% para el resto
def obtener_tope_descuento(producto: dict) -> Decimal:
    topes_descuento = leer_reglas()["topes_descuento"]
    es_herramienta_electrica = producto["rubro"].lower().startswith("herramienta")
    if es_herramienta_electrica and producto["marca"].lower() in topes_descuento["marcas_herramienta_electrica"]:
        return convertir_a_decimal(topes_descuento["tope_herramienta_electrica"])
    return convertir_a_decimal(topes_descuento["tope_general"])


# revisa si el pedido se paga con cuenta corriente (con crédito)
# (los pagos anticipados y al contado no usan crédito)
# (si un cliente categoría C no dice cómo paga se toma como contado según el art. 6)
def usa_cuenta_corriente(cliente: dict, forma_pago: str) -> bool:
    if forma_pago in ("anticipado", "contado"):
        return False
    if cliente["categoria"] == "C" and forma_pago == "no_indicada":
        return False
    return True


# revisa que el pedido cumpla todas las reglas y decide: confirmar, humano (lo aprueba Gerencia), rechazar o derivar
# devuelve la decisión con sus motivos, los productos con su descuento, los montos y el crédito del cliente
# (descuento_autorizado solo llega cuando Gerencia ya aprobó y hay que recalcular el pedido)
def evaluar_pedido(cliente: dict | None, pedido: dict, descuento_autorizado=None) -> dict:
    reglas = leer_reglas()
    descuento_autorizado = validar_descuento(descuento_autorizado)
    motivos_derivacion, motivos_rechazo, motivos_aprobacion = [], [], []
    items = pedido.get("items")
    if not items:
        items = []

    if cliente is None:
        motivos_derivacion.append("El CUIT no pertenece a ningún cliente registrado")
    if not items:
        motivos_derivacion.append("El mensaje no menciona ningún producto")

    # 1. busca cada producto con la tool
    productos_encontrados = []
    for item in items:
        if not item.get("sku"):
            motivos_derivacion.append(f"No se pudo identificar el producto '{item.get('descripcion', '?')}'")
            continue
        producto = consultar_producto.invoke({"sku": item["sku"], "cantidad": item["cantidad"]})
        if not producto["encontrado"]:
            motivos_derivacion.append(producto["error"])
            continue
        if not producto["stock_suficiente"]:
            motivos_aprobacion.append(f"No hay stock suficiente de {producto['sku']}: piden {item['cantidad']} y hay {producto['stock']} (art. 9)")
        productos_encontrados.append((producto, item["cantidad"]))

    if motivos_derivacion:
        # si falta algo no tiene sentido calcular precios y corta acá
        return {"decision": "derivar", "motivos_derivacion": motivos_derivacion, "motivos_rechazo": [],
                "motivos_aprobacion": motivos_aprobacion, "productos": [], "montos": {}, "credito": {}}

    # 2. calcula precios y descuentos
    monto_lista = sum((convertir_a_decimal(producto["precio_lista"]) * cantidad for producto, cantidad in productos_encontrados), Decimal(0))
    descuento_volumen = calcular_descuento_volumen(monto_lista)
    descuento_habitual = convertir_a_decimal(cliente["descuento_habitual"])
    descuento_solicitado = None
    if pedido.get("descuento_solicitado") is not None:
        descuento_solicitado = convertir_a_decimal(pedido["descuento_solicitado"])

    forma_pago = pedido.get("forma_pago", "no_indicada")
    descuento_financiero = Decimal(0)
    if forma_pago == "anticipado":
        descuento_financiero = convertir_a_decimal(reglas["pago_anticipado"]["descuento_financiero"])

    productos = []
    productos_tope_excedido = []   # productos donde el descuento que pide el cliente supera el tope de ese producto
    tope_general = convertir_a_decimal(reglas["topes_descuento"]["tope_general"])
    for producto, cantidad in productos_encontrados:
        tope = obtener_tope_descuento(producto)
        descuento_aplicado = min(descuento_habitual + descuento_volumen, tope)  # nunca más que el tope, aunque la suma dé más
        se_mantuvo_tope_marca = False
        if descuento_autorizado is not None:
            # Gerencia puede pasar el 20% general (art. 5), pero el 15% de Dewalt, Makita y Bosch
            # es un acuerdo con el fabricante, así que se mantiene aunque autorice más
            descuento_aplicado = max(descuento_aplicado, descuento_autorizado)
            if tope < tope_general and descuento_aplicado > tope:
                descuento_aplicado = tope
                se_mantuvo_tope_marca = True
        elif descuento_solicitado is not None:
            if descuento_solicitado > tope:
                # se compara con el tope de ESTE producto: 19% en una Dewalt ya se pasa del 15%
                productos_tope_excedido.append(f"{producto['sku']} hasta {float(tope):g}%")
            else:
                descuento_aplicado = max(descuento_aplicado, descuento_solicitado)   # si lo que pide está dentro del tope, se le da
        monto_lista_producto = convertir_a_decimal(producto["precio_lista"]) * cantidad
        monto_con_descuento = monto_lista_producto * (1 - descuento_aplicado / 100)
        monto_con_descuento = monto_con_descuento * (1 - descuento_financiero / 100)  # el 3% anticipado va aparte del tope (art. 6)
        productos.append({
            "sku": producto["sku"], "nombre": producto["nombre"], "cantidad": cantidad, "stock": producto["stock"],
            "precio_lista": convertir_a_decimal(producto["precio_lista"]), "descuento_aplicado": descuento_aplicado,
            "monto_con_descuento": redondear_monto(monto_con_descuento), "deposito": producto["deposito"], "se_mantuvo_tope_marca": se_mantuvo_tope_marca,
        })
    monto_con_descuento = sum((producto["monto_con_descuento"] for producto in productos), Decimal(0))
    if productos_tope_excedido:
        motivos_aprobacion.append(f"Pide {float(descuento_solicitado):g}% de descuento y supera el tope permitido: "
                                  f"{', '.join(productos_tope_excedido)} (art. 5)")

    # 3. revisa el pedido mínimo (art. 3): no se rechaza, queda en espera y lo ve una persona
    minimo = convertir_a_decimal(reglas["pedido_minimo"][cliente["categoria"]])
    if monto_con_descuento < minimo:
        motivos_aprobacion.append(f"El monto neto del pedido ({formatear_monto(monto_con_descuento)}) no llega al "
                                  f"pedido mínimo de {formatear_monto(minimo)} (art. 3)")

    # 4. revisa crédito y mora con la otra tool (art. 6 y 7)
    es_cuenta_corriente = usa_cuenta_corriente(cliente, forma_pago)
    credito = verificar_credito.invoke({"cuit": cliente["cuit"], "monto_pedido": monto_con_descuento})
    
    # la tool devuelve los montos como texto, así que los vuelve a pasar a Decimal
    for campo in ("limite_credito", "saldo_actual", "credito_disponible", "monto_pedido", "saldo_despues"):
        credito[campo] = convertir_a_decimal(credito[campo])
    credito["usa_cuenta_corriente"] = es_cuenta_corriente
    mora = reglas["mora"]

    # con más de 60 días de mora solo se acepta pago anticipado (art. 7)
    suspendido = credito["estado"] == "suspendido" or credito["mora_dias"] > mora["suspension"]
    if suspendido and forma_pago != "anticipado":
        motivos_rechazo.append(f"Cliente suspendido con {credito['mora_dias']} días de mora: "
                               "solo puede comprar con pago anticipado (art. 7)")

    # mora de 30 a 60: el art. 7 dice "cada pedido", así que va aunque pague anticipado
    if mora["desde_autorizacion"] <= credito["mora_dias"] <= mora["suspension"]:
        motivos_aprobacion.append(f"Tiene {credito['mora_dias']} días de mora: con 30 a 60 días de mora "
                                  "cada pedido necesita autorización (art. 7)")

    if es_cuenta_corriente and not suspendido:
        if not credito["entra_en_limite"]:
            motivos_aprobacion.append(f"El saldo actual ({formatear_monto(credito['saldo_actual'])}) más el monto de este pedido "
                                      f"({formatear_monto(monto_con_descuento)}) da un total de "
                                      f"{formatear_monto(credito['saldo_despues'])}, que supera el límite de crédito "
                                      f"de {formatear_monto(credito['limite_credito'])} (art. 7)")
        if cliente["categoria"] == "C":
            motivos_aprobacion.append("Es categoría C y pide cuenta corriente: necesita autorización (art. 6)")
        plazo = pedido.get("plazo_dias")
        if plazo and plazo > int(cliente["dias_plazo"]):
            motivos_aprobacion.append(f"Pide {plazo} días de plazo y le corresponden {cliente['dias_plazo']} (art. 6)")

    # 5. estima los impuestos (art. 2 y 8). La percepción de IIBB depende del padrón, que no está en los datos
    impuestos = reglas["impuestos"]
    iva = monto_con_descuento * convertir_a_decimal(impuestos["iva"]) / 100
    percepcion_iibb = Decimal(0)
    if cliente["provincia"].lower() != "cordoba":
        percepcion_iibb = monto_con_descuento * convertir_a_decimal(impuestos["percepcion_iibb_fuera_de_cordoba"]) / 100
    percepcion_iva = Decimal(0)
    if cliente["condicion_iva"] == "Responsable Inscripto" and monto_con_descuento > convertir_a_decimal(impuestos["percepcion_iva_desde_neto"]):
        percepcion_iva = monto_con_descuento * convertir_a_decimal(impuestos["percepcion_iva"]) / 100

    montos = {
        "monto_lista": redondear_monto(monto_lista),
        "descuento_volumen": descuento_volumen,
        "descuento_habitual": descuento_habitual,
        "descuento_financiero": descuento_financiero,
        "monto_con_descuento": redondear_monto(monto_con_descuento),
        "iva": redondear_monto(iva),
        "percepcion_iibb": redondear_monto(percepcion_iibb),
        "percepcion_iva": redondear_monto(percepcion_iva),
        "monto_final": redondear_monto(monto_con_descuento + iva + percepcion_iibb + percepcion_iva),
        "forma_pago": forma_pago,
    }

    if motivos_rechazo:
        decision = "rechazar"
    elif motivos_aprobacion:
        decision = "humano"
    else:
        decision = "confirmar"

    return {"decision": decision, "motivos_derivacion": [], "motivos_rechazo": motivos_rechazo,
            "motivos_aprobacion": motivos_aprobacion, "productos": productos, "montos": montos, "credito": credito}


# arma la entrega parcial cuando Gerencia aprueba un pedido sin stock suficiente (art. 9)
# separa el pedido en lo que se envía ahora y lo que queda pendiente (ej. piden 60 y hay 52: se envían 52 y quedan 8 pendientes)
def armar_entrega_parcial(pedido: dict) -> tuple[dict, list[dict]]:
    items_parciales = []
    pendientes = []

    for item in pedido["items"]:
        producto = consultar_producto.invoke({"sku": item["sku"], "cantidad": item["cantidad"]})
        if not producto["encontrado"]:
            raise ValueError(producto["error"])   # no debería pasar (validar_pedido lo deriva)

        cantidad_a_enviar = min(item["cantidad"], max(0, producto["stock"]))
        cantidad_faltante = item["cantidad"] - cantidad_a_enviar

        if cantidad_faltante > 0:
            pendientes.append({"sku": item["sku"], "nombre": producto["nombre"], "cantidad": cantidad_faltante})
        if cantidad_a_enviar > 0:
            item_parcial = dict(item)  # copia el item para no cambiar el pedido original
            item_parcial["cantidad"] = cantidad_a_enviar
            items_parciales.append(item_parcial)

    entrega_parcial = dict(pedido)
    entrega_parcial["items"] = items_parciales
    return entrega_parcial, pendientes