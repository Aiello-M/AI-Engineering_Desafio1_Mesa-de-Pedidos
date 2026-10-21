""" Corre los 20 mensajes de la bandeja y compara los resultados con el golden set
    (ruta, intención, dato clave, documento citado y productos del pedido)
"""

import argparse
import json
import re
import time
import unicodedata
from langgraph.checkpoint.memory import InMemorySaver
import config
from mesa_pedidos.grafo import armar_config_hilo, construir_grafo


# pasa el texto a minúsculas sin tildes y escribe los n° siempre igual para poder comparar
def normalizar_texto(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto).lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    # 1.500.000 y 1500000 quedan iguales
    texto = re.sub(r"(?<=\d)[.,](?=\d{3}\b)", "", texto)
    # "5 %" queda "5%"
    texto = re.sub(r"(\d)\s+%", r"\1%", texto)
    return texto


# verifica que la rta tenga el dato clave
def tiene_dato_clave(respuesta: str, dato: str) -> bool:
    respuesta = normalizar_texto(respuesta)
    dato = normalizar_texto(dato)
    if dato.isalpha() or dato.isdigit():
        # busca la palabra completa (así el 5 no cuenta dentro del 15)
        return re.search(rf"(?<![\w.]){re.escape(dato)}(?![\w])", respuesta) is not None
    return dato in respuesta


# devuelve el nodo donde terminó el msj (o donde quedó frenado esperando a Gerencia)
def obtener_ruta(grafo, config_hilo) -> str:
    estado = grafo.get_state(config_hilo)
    if estado.next:
        return estado.next[0]
    return estado.values.get("nodo_final", "?")


# compara los productos que extrajo el LLM con los del golden set (SKU y cantidad)
# devuelve la cant de aciertos, de extraídos y de esperados
def comparar_productos(esperados: list[dict], extraidos: list[dict]) -> tuple[int, int, int]:
    pares_esperados = {(item["sku"], item["cantidad"]) for item in esperados}
    pares_extraidos = {(item.get("sku"), item.get("cantidad")) for item in extraidos}
    aciertos = len(pares_esperados & pares_extraidos)
    return aciertos, len(pares_extraidos), len(pares_esperados)


# arma un archivo con las 8 respuestas para revisarlas a mano
# (el dato clave puede aparecer aunque la respuesta esté mal)
def escribir_revision_manual(consultas: list[dict], ruta) -> None:
    lineas = ["# Revisión manual de las 8 consultas", ""]
    for fila in consultas:
        lineas.append(f"## {fila['id']}")
        lineas.append(f"Pregunta: {fila['texto']}")
        lineas.append(f"Dato clave esperado: {', '.join(fila['debe_contener'])}")
        lineas.append(f"Documento esperado: {fila['documento_esperado']}")
        lineas.append(f"Respuesta: {fila['respuesta']}")
        lineas.append("¿Está bien?: ")
        lineas.append("")
    ruta.write_text("\n".join(lineas), encoding="utf-8")


# corre los 20 mensajes, compara c/u con el golden set y guarda el resumen y detalle
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--densa", action="store_true", help="usar solo búsqueda por embeddings")
    args = parser.parse_args()
    if args.densa:
        config.USAR_HIBRIDO = False

    golden = {caso["id"]: caso for caso in json.loads(config.GOLDEN_SET.read_text(encoding="utf-8"))["casos"]}
    bandeja = [json.loads(linea) for linea in config.BANDEJA.read_text(encoding="utf-8").splitlines() if linea.strip()]

    # guarda el estado en memoria (así las pruebas no se mezclan con los pedidos reales)
    grafo = construir_grafo(InMemorySaver())
    corrida = time.strftime("%Y%m%d-%H%M%S")
    resultados = []
    total_aciertos = 0
    total_extraidos = 0
    total_esperados = 0

    for mensaje in bandeja:
        esperado = golden[mensaje["id"]]
        config_hilo = armar_config_hilo(f"eval-{corrida}-{mensaje['id']}")
        # si un caso falla se anota el error y se sigue con los demás
        try:
            grafo.invoke({"id_mensaje": mensaje["id"], "cuit": mensaje["cuit"], "texto": mensaje["texto"],
                          "fecha": mensaje.get("fecha", ""), "log": []}, config_hilo)
            error = None
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
        valores = grafo.get_state(config_hilo).values
        if error:
            ruta = "ERROR"
        else:
            ruta = obtener_ruta(grafo, config_hilo)

        fila = {
            "id": mensaje["id"], "texto": mensaje["texto"],
            "intencion_esperada": esperado["intencion"], "intencion_obtenida": valores.get("intencion"),
            "ruta_esperada": esperado["ruta"], "ruta_obtenida": ruta, "ruta_ok": ruta == esperado["ruta"],
            "log": valores.get("log", []), "error": error,
        }
        if esperado["intencion"] == "consulta":
            respuesta = valores.get("respuesta", "")
            documentos = {fuente["documento"] for fuente in valores.get("fuentes", [])}
            dato_clave_ok = bool(respuesta) and all(tiene_dato_clave(respuesta, dato) for dato in esperado["debe_contener"])
            fila.update({"respuesta": respuesta, "debe_contener": esperado["debe_contener"],
                         "fuentes_recuperadas": valores.get("fuentes", []),
                         "dato_clave_ok": dato_clave_ok,
                         "documento_esperado": esperado["documento"],
                         "documento_recuperado": esperado["documento"] in documentos,
                         # verifica que la rta cite el documento
                         "documento_citado": esperado["documento"] in respuesta})
        if "items" in esperado:
            pedido = valores.get("pedido")
            if pedido:
                extraidos = pedido.get("items", [])
            else:
                extraidos = []
            validacion = valores.get("validacion")
            if validacion:
                motivos_aprobacion = validacion.get("motivos_aprobacion", [])
            else:
                motivos_aprobacion = []
            aciertos, cantidad_extraidos, cantidad_esperados = comparar_productos(esperado["items"], extraidos)
            total_aciertos += aciertos
            total_extraidos += cantidad_extraidos
            total_esperados += cantidad_esperados
            fila.update({"items_esperados": esperado["items"], "items_extraidos": extraidos,
                         "motivos_aprobacion": motivos_aprobacion})
        resultados.append(fila)

        if fila["ruta_ok"]:
            texto_ruta = f"ruta OK ({ruta})"
        else:
            texto_ruta = f"ruta NO (fue a {ruta} y tenía que ir a {esperado['ruta']})"
        dato_clave = ""
        if "dato_clave_ok" in fila:
            if fila["dato_clave_ok"]:
                dato_clave = ", dato clave OK"
            else:
                dato_clave = ", dato clave NO"
        print(f"{mensaje['id']}: {texto_ruta}{dato_clave}")

    consultas = [fila for fila in resultados if "dato_clave_ok" in fila]
    if args.densa:
        busqueda = "densa"
        salida = config.RAIZ / "evaluacion_densa.json"
    else:
        busqueda = "híbrida (embeddings + BM25)"
        salida = config.EVALUACION_JSON
    if total_extraidos:
        items_precision = round(total_aciertos / total_extraidos, 3)
    else:
        items_precision = None
    if total_esperados:
        items_recall = round(total_aciertos / total_esperados, 3)
    else:
        items_recall = None

    resumen = {
        "configuracion": {"modelo": config.MODELO_LLM, "embeddings": config.MODELO_EMBEDDINGS, "busqueda": busqueda},
        "ruta_correcta": f"{sum(fila['ruta_ok'] for fila in resultados)}/{len(resultados)}",
        "consultas_con_dato_clave": f"{sum(fila['dato_clave_ok'] for fila in consultas)}/{len(consultas)}",
        "intencion_correcta": f"{sum(fila['intencion_obtenida'] == fila['intencion_esperada'] for fila in resultados)}/{len(resultados)}",
        "consultas_con_documento_recuperado": f"{sum(fila['documento_recuperado'] for fila in consultas)}/{len(consultas)}",
        "consultas_que_citan_el_documento": f"{sum(fila['documento_citado'] for fila in consultas)}/{len(consultas)}",
        "items_precision": items_precision,
        "items_recall": items_recall,
    }
    salida.write_text(json.dumps({"resumen": resumen, "casos": resultados}, ensure_ascii=False,
                                 indent=2, default=str), encoding="utf-8")

    print("\nResumen:")
    print(f"Búsqueda: {busqueda}")
    print(f"Ruta correcta: {resumen['ruta_correcta']}")
    print(f"Consultas con el dato clave: {resumen['consultas_con_dato_clave']}")
    print(f"Intención correcta: {resumen['intencion_correcta']}")
    print(f"Consultas que recuperan el documento: {resumen['consultas_con_documento_recuperado']}")
    print(f"Consultas que citan el documento: {resumen['consultas_que_citan_el_documento']}")
    print(f"Precisión de los productos: {resumen['items_precision']}")
    print(f"Recall de los productos: {resumen['items_recall']}")
    print(f"\nLos resultados quedaron guardados en {salida.name}")

    # arma la revisión a mano solo con la búsqueda híbrida (así no se pisa al correr con densa)
    if not args.densa:
        escribir_revision_manual(consultas, config.RAIZ / "revision_consultas.md")
        print("Las 8 respuestas para revisar a mano están en revision_consultas.md")


if __name__ == "__main__":
    main()