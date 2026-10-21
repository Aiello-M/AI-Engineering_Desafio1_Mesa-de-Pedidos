""" Los 9 nodos del grafo. """

from langgraph.types import interrupt
from mesa_pedidos import llm, retriever
from mesa_pedidos.datos import leer_clientes, normalizar_cuit
from mesa_pedidos.reglas import calcular_dias, evaluar_pedido, armar_entrega_parcial, formatear_monto, validar_descuento

# arma una línea con los datos del cliente para el LLM
def describir_cliente(cliente: dict | None) -> str:
    if not cliente:
        return "El CUIT no pertenece a ningún cliente registrado"
    return (f"Razón social: {cliente['razon_social']}, localidad: {cliente['localidad']}, "
            f"provincia: {cliente['provincia']}, condición de IVA: {cliente['condicion_iva']}, "
            f"categoría: {cliente['categoria']}, plazo de pago: {cliente['dias_plazo']} días")


# nodo 1: busca el cliente por CUIT (si no existe queda en None)
def cargar_cliente(state: dict) -> dict:
    cliente = leer_clientes().get(normalizar_cuit(state["cuit"]))
    if cliente:
        linea = f"cargar_cliente: {cliente['razon_social']}"
    else:
        linea = f"cargar_cliente: CUIT {state['cuit']} no encontrado"
    return {"cliente": cliente, "log": [linea]}


# nodo 2: clasifica el mensaje con el LLM (consulta, pedido o derivar)
def clasificar(state: dict) -> dict:
    clasificacion = llm.clasificar_mensaje(state["texto"], state.get("fecha", ""))
    linea = f"clasificar: {clasificacion.intencion} ({clasificacion.motivo})"
    if clasificacion.fecha_mencionada:
        linea += f", menciona la fecha {clasificacion.fecha_mencionada}"
    return {"intencion": clasificacion.intencion, "motivo_clasificacion": clasificacion.motivo,
            "fecha_mencionada": clasificacion.fecha_mencionada, "log": [linea]}


# nodo 3: busca en los PDF y le pide al LLM la respuesta con citas
def responder_consulta(state: dict) -> dict:
    chunks = retriever.recuperar(state["texto"])
    fuentes = [{"documento": chunk.metadata["documento"], "pagina": chunk.metadata["pagina"]} for chunk in chunks]
    # cuenta en Python los días entre fechas (para que el LLM no se equivoque)
    calculo_dias = calcular_dias(state.get("fecha_mencionada"), state.get("fecha"))
    # se necesitan los datos del cliente para la zona de flete y la percepción
    respuesta = llm.responder_consulta(
        pregunta=state["texto"],
        contexto=retriever.formatear_contexto(chunks),
        cliente=describir_cliente(state.get("cliente")),
        fecha=state.get("fecha", ""),
        calculo_dias=calculo_dias,
    )
    citas = sorted({f"{fuente['documento']} p.{fuente['pagina']}" for fuente in fuentes})
    return {"respuesta": respuesta, "fuentes": fuentes, "nodo_final": "responder_consulta",
            "log": [f"responder_consulta: {len(chunks)} fragmentos ({', '.join(citas)})"]}


# nodo 4: saca del mensaje los productos y las condiciones del pedido con el LLM
def extraer_pedido(state: dict) -> dict:
    pedido = llm.extraer_pedido(state["texto"])
    items = ", ".join(f"{item.cantidad} x {item.sku}" for item in pedido.items)
    if not items:
        items = "sin productos"
    return {"pedido": pedido.model_dump(), "log": [f"extraer_pedido: {items}"]}


# nodo 5: revisa el pedido con las tools y las reglas (sin LLM) y decide qué hacer
def validar_pedido(state: dict) -> dict:
    validacion = evaluar_pedido(state.get("cliente"), state["pedido"])
    motivos = validacion["motivos_derivacion"] + validacion["motivos_rechazo"] + validacion["motivos_aprobacion"]
    monto_con_descuento = validacion["montos"].get("monto_con_descuento")
    linea = f"validar_pedido: {validacion['decision']}"
    if monto_con_descuento:
        linea += f", monto con descuento {formatear_monto(monto_con_descuento)}"
    if motivos:
        linea += " (motivos: " + "; ".join(motivos) + ")"
    return {"validacion": validacion, "decision_validacion": validacion["decision"], "log": [linea]}


# nodo 6: frena el pedido hasta que Gerencia lo apruebe o lo rechace
def aprobacion_humana(state: dict) -> dict:
    validacion = state["validacion"]
    cliente = state["cliente"]

    # arma la entrega parcial con el stock que hay y calcula su monto
    entrega_parcial, pendientes = armar_entrega_parcial(state["pedido"])
    monto_con_stock = None
    if entrega_parcial["items"]:
        validacion_parcial = evaluar_pedido(cliente, entrega_parcial)
        monto_con_stock = validacion_parcial["montos"]["monto_con_descuento"]

    payload = {
        "tipo": "aprobacion_pedido",
        "id_mensaje": state["id_mensaje"],
        "razon_social": cliente["razon_social"],
        "cuit": cliente["cuit"],
        "categoria": cliente["categoria"],
        "credito_disponible": validacion["credito"]["credito_disponible"],
        "saldo_actual": validacion["credito"]["saldo_actual"],
        "limite_credito": validacion["credito"]["limite_credito"],
        "mora_dias": validacion["credito"]["mora_dias"],
        "monto_con_descuento": validacion["montos"]["monto_con_descuento"],
        "monto_final": validacion["montos"]["monto_final"],
        "motivos_aprobacion": validacion["motivos_aprobacion"],
        "productos": validacion["productos"],
        "descuento_pedido_por_cliente": state["pedido"].get("descuento_solicitado"),
        "monto_con_stock_disponible": monto_con_stock,
        "pendientes": pendientes,
        "mensaje_original": state["texto"],
       
        "si_aprobas": ("Si aprobás, se envía solo lo que hay en stock y lo que falta queda pendiente "
                       "para otra entrega (art. 9). Se aplica el descuento que le corresponde al cliente "
                       "(habitual + volumen, con su tope), salvo que autorices otro. Dewalt, Makita y Bosch "
                       "siguen con tope de 15% aunque autorices más (art. 5)."),
    }
    respuesta = interrupt(payload)

    # si la respuesta no es un sí claro se toma como rechazo
    accion = str(respuesta.get("accion", "")).lower()
    if accion in ("aprobar", "aprueba", "si", "sí"):
        accion = "aprobar"
    else:
        accion = "rechazar"
    decision = {"accion": accion, "comentario": respuesta.get("comentario", ""),
                "descuento_autorizado": None, "ruta": "rechaza"}

    if accion == "rechazar":
        return {"decision_humana": decision, "log": ["aprobacion_humana: rechazado por Gerencia"]}

    decision["descuento_autorizado"] = validar_descuento(respuesta.get("descuento_autorizado"))

    # aunque Gerencia apruebe, tiene que quedar algo para confirmar
    if not entrega_parcial["items"]:
        decision["motivo_bloqueo"] = "Gerencia aprobó el pedido, pero no hay stock de ninguno de los productos"
        return {"decision_humana": decision, "log": ["aprobacion_humana: aprobado pero sin stock"]}

    validacion_final = evaluar_pedido(cliente, entrega_parcial, decision["descuento_autorizado"])
    if validacion_final["decision"] in ("rechazar", "derivar") or validacion_final["montos"]["monto_con_descuento"] <= 0:
        decision["motivo_bloqueo"] = "Gerencia aprobó el pedido, pero al volver a revisarlo no cumple las condiciones para confirmarse"
        return {"decision_humana": decision, "log": ["aprobacion_humana: aprobado pero no confirmable"]}

    decision["ruta"] = "aprueba"
    linea = "aprobacion_humana: aprobado"
    if decision["descuento_autorizado"] is not None:
        linea += f", descuento autorizado {float(decision['descuento_autorizado']):g}%"
    if decision["comentario"]:
        linea += f" ({decision['comentario']})"
    return {"decision_humana": decision, "validacion_final": validacion_final, "pendientes": pendientes, "log": [linea]}


# nodo 7: arma el texto de confirmación (usando el pedido recalculado si pasó por Gerencia)
def confirmar_pedido(state: dict) -> dict:
    if state.get("validacion_final"):
        validacion = state["validacion_final"]
    else:
        validacion = state["validacion"]
    aprobacion = state.get("decision_humana")
    pendientes = state.get("pendientes", [])
    montos = validacion["montos"]

    texto = f"Pedido confirmado para {state['cliente']['razon_social']}\n"
    for producto in validacion["productos"]:
        texto += (f"  {producto['cantidad']} x {producto['sku']} {producto['nombre']} - "
                  f"{float(producto['descuento_aplicado']):g}% de descuento")
        if producto.get("se_mantuvo_tope_marca"):
            texto += " (tope de la marca, art. 5)"
        texto += f" - {formatear_monto(producto['monto_con_descuento'], 2)}\n"
    # p: cada producto pendiente
    for p in pendientes:
        texto += f"  Queda pendiente por falta de stock: {p['cantidad']} x {p['sku']} {p['nombre']}\n"
    percepciones = montos["percepcion_iibb"] + montos["percepcion_iva"]
    texto += f"  Neto: {formatear_monto(montos['monto_con_descuento'], 2)}\n"
    texto += f"  IVA: {formatear_monto(montos['iva'], 2)}\n"
    texto += f"  Percepciones estimadas: {formatear_monto(percepciones, 2)}\n"
    texto += f"  Total: {formatear_monto(montos['monto_final'], 2)} (sin flete)"
    if aprobacion:
        texto += "\n  Aprobado por Gerencia Comercial"
        if aprobacion.get("comentario"):
            texto += f": {aprobacion['comentario']}"

    linea = f"confirmar_pedido: monto con descuento {formatear_monto(montos['monto_con_descuento'])}"
    if len(pendientes) == 1:
        linea += ", 1 producto pendiente"
    elif len(pendientes) > 1:
        linea += f", {len(pendientes)} productos pendientes"
    confirmacion = {"productos": validacion["productos"], "montos": montos, "pendientes": pendientes}
    return {"respuesta": texto, "confirmacion": confirmacion, "nodo_final": "confirmar_pedido", "log": [linea]}


# nodo 8: arma el texto de rechazo con el motivo
def rechazar_pedido(state: dict) -> dict:
    decision = state.get("decision_humana")
    if decision:
        # puede venir de un rechazo de gerencia o de una aprobación que no se pudo confirmar
        motivo = decision.get("motivo_bloqueo")
        if not motivo:
            motivo = "Gerencia Comercial no aprobó el pedido"
        if decision.get("comentario"):
            motivo += f" ({decision['comentario']})"
        texto = f"Pedido rechazado. {motivo}."
    else:
        motivo = "; ".join(state["validacion"]["motivos_rechazo"])
        texto = f"Pedido rechazado. {motivo}."
    return {"respuesta": texto, "nodo_final": "rechazar_pedido", "log": [f"rechazar_pedido: {motivo}"]}


# nodo 9: pasa el mensaje al equipo comercial con el motivo
# (llega desde clasificar o desde validar_pedido)
def derivar_humano(state: dict) -> dict:
    if state.get("validacion"):
        motivo = "; ".join(state["validacion"]["motivos_derivacion"])
    else:
        motivo = state.get("motivo_clasificacion", "no se pudo clasificar el mensaje")
    return {"respuesta": f"Mensaje derivado al equipo comercial. Motivo: {motivo}",
            "nodo_final": "derivar_humano", "log": [f"derivar_humano: {motivo}"]}