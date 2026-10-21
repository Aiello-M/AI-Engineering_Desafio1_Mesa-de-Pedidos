""" Corre un mensaje de la bandeja y maneja la aprobación de Gerencia
    (el estado de cada pedido queda guardado para retomarlo después)
"""

import argparse
import json
import uuid
from langgraph.types import Command
import config
from mesa_pedidos.grafo import abrir_grafo_persistente, armar_config_hilo
from mesa_pedidos.reglas import formatear_monto, validar_descuento


# busca el msj por id en la bandeja
def leer_mensaje(id_mensaje: str) -> dict:
    with open(config.BANDEJA, encoding="utf-8") as f:
        for linea in f:
            mensaje = json.loads(linea)
            if mensaje["id"] == id_mensaje:
                return mensaje
    raise SystemExit(f"No existe {id_mensaje} en {config.BANDEJA.name}")


# revisa si el pedido quedó esperando a Gerencia y no cortado por un error
def esperando_aprobacion(estado) -> bool:
    return any(tarea.interrupts for tarea in estado.tasks)


# muestra los datos que Gerencia necesita para aprobar o rechazar
def mostrar_pendiente(estado) -> None:
    payload = estado.tasks[0].interrupts[0].value
    print("\nPedido en espera: necesita la aprobación de Gerencia Comercial")
    print(f"   Cliente: {payload['razon_social']} ({payload['cuit']}), categoría {payload['categoria']}")
    print(f"   Crédito disponible: {formatear_monto(payload['credito_disponible'])} "
          f"(límite: {formatear_monto(payload['limite_credito'])}, saldo: {formatear_monto(payload['saldo_actual'])}), "
          f"mora: {payload['mora_dias']} días")
    print(f"   Neto: {formatear_monto(payload['monto_con_descuento'], 2)}")
    print("   Productos:")
    for producto in payload["productos"]:
        print(f"     {producto['cantidad']:>4} x {producto['sku']} {producto['nombre']} - "
              f"{float(producto['descuento_aplicado']):g}% de descuento - {formatear_monto(producto['monto_con_descuento'], 2)}")
    print("   Motivos para aprobar:")
    for motivo in payload["motivos_aprobacion"]:
        print(f"     - {motivo}")
    if payload["pendientes"]:
        faltan = ", ".join(f"{p['cantidad']} x {p['sku']}" for p in payload["pendientes"])
        monto_con_stock = payload["monto_con_stock_disponible"]
        if monto_con_stock is not None:
            texto_monto = formatear_monto(monto_con_stock, 2)
        else:
            texto_monto = "$0,00 (no hay stock de ningún producto)"
        print(f"   Sin stock: {faltan}. Con lo que hay, el neto sería {texto_monto}")
    if payload["descuento_pedido_por_cliente"] is not None:
        print(f"   El cliente pidió {float(payload['descuento_pedido_por_cliente']):g}% de descuento")
    print(f"   {payload['si_aprobas']}")
    hilo = estado.config["configurable"]["thread_id"]
    print("\n   Para decidir (ahora o más tarde):")
    print(f"     python correr.py {hilo} --aprobar \"comentario\"")
    print(f"     python correr.py {hilo} --aprobar \"comentario\" --descuento 22")
    print(f"     python correr.py {hilo} --rechazar \"comentario\"")


# muestra la respuesta final y el log con una línea por nodo
def mostrar_final(valores: dict) -> None:
    print("\n" + "-" * 70)
    print(f"Terminó en: {valores.get('nodo_final')}\n")
    print(valores.get("respuesta", ""))
    print("\nLog:")
    for linea in valores.get("log", []):
        print(f"  {linea}")


# revisa el descuento ingresado antes de retomar el pedido
def revisar_descuento_ingresado(valor: str):
    try:
        return validar_descuento(valor)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))


# corre el mensaje de la bandeja (o retoma el pedido que esperaba gerencia)
def main():
    parser = argparse.ArgumentParser(description="Mesa de Pedidos")
    parser.add_argument("id", nargs="?", help="ID del mensaje de la bandeja, ej. MSG-009")
    parser.add_argument("--texto", help="procesar un mensaje escrito a mano")
    parser.add_argument("--cuit", help="CUIT para usar con --texto")
    parser.add_argument("--fecha", help="fecha del mensaje (AAAA-MM-DD) para usar con --texto")
    parser.add_argument("--aprobar", metavar="COMENTARIO", nargs="?", const="")
    parser.add_argument("--rechazar", metavar="COMENTARIO", nargs="?", const="")
    parser.add_argument("--descuento", type=revisar_descuento_ingresado,
                        help="con --aprobar: descuento que autoriza Gerencia, en %%")
    parser.add_argument("--estado", action="store_true")
    args = parser.parse_args()
    if args.aprobar is not None and args.rechazar is not None:
        parser.error("No se puede aprobar y rechazar a la vez")
    if args.descuento is not None and args.aprobar is None:
        parser.error("Solo se puede aplicar un descuento al aprobar el pedido (--descuento va con --aprobar)")

    if args.texto:
        mensaje = {"id": args.id, "cuit": args.cuit, "texto": args.texto, "fecha": args.fecha}
        if not args.id:
            mensaje["id"] = f"LIBRE-{uuid.uuid4().hex[:6]}"
        if not args.cuit:
            mensaje["cuit"] = ""
        if not args.fecha:
            mensaje["fecha"] = ""
    elif args.id:
        mensaje = leer_mensaje(args.id)
    else:
        parser.error("Falta el mensaje: indicá el id de la bandeja (ej. MSG-009) o escribí un mensaje con --texto")

    config_hilo = armar_config_hilo(mensaje["id"])
    with abrir_grafo_persistente() as grafo:
        estado = grafo.get_state(config_hilo)

        if args.aprobar is not None or args.rechazar is not None:
            if not estado.next:
                raise SystemExit(f"{mensaje['id']} no tiene ninguna aprobación pendiente.")
            if args.aprobar is not None:
                accion = "aprobar"
                comentario = args.aprobar
            else:
                accion = "rechazar"
                comentario = args.rechazar
            # envía la decisión de Gerencia al pedido
            decision = {"accion": accion, "comentario": comentario}
            if args.descuento is not None:
                decision["descuento_autorizado"] = str(args.descuento)
            grafo.invoke(Command(resume=decision), config_hilo)

        elif args.estado:
            if not estado.values:
                print(f"El mensaje {mensaje['id']} todavía no se procesó")
            elif estado.next:
                print(f"El próximo nodo del mensaje {mensaje['id']} es {estado.next[0]}")
            else:
                print(f"El mensaje {mensaje['id']} ya terminó (no tiene próximo nodo)")
            print(json.dumps({k: v for k, v in estado.values.items() if k != "cliente"},
                             ensure_ascii=False, indent=2, default=str))
            return

        elif not estado.values:
            print(f"Procesando {mensaje['id']}: {mensaje['texto']}")
            grafo.invoke({"id_mensaje": mensaje["id"], "cuit": mensaje["cuit"], "texto": mensaje["texto"],
                          "fecha": mensaje.get("fecha", ""), "log": []}, config_hilo)
        elif estado.next and not esperando_aprobacion(estado):
            # retoma desde donde se quedó (si antes se había cortado el msj por la mitad)
            print(f"El mensaje {mensaje['id']} se había interrumpido: sigue desde el nodo {estado.next[0]}.")
            grafo.invoke(None, config_hilo)
        else:
            # si ya se procesó solo muestra cómo quedó
            print(f"El mensaje {mensaje['id']} ya fue procesado. Resultado:")

        estado = grafo.get_state(config_hilo)
        if esperando_aprobacion(estado):
            mostrar_pendiente(estado)
        else:
            mostrar_final(estado.values)


if __name__ == "__main__":
    main()