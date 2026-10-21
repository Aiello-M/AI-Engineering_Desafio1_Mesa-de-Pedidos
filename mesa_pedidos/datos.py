""" Lee catalogo.csv y clientes.csv. """

from functools import lru_cache
import pandas as pd
import config


# convierte el CUIT al formato del CSV (30-70988341-7) por si llega sin guiones o con espacios
def normalizar_cuit(cuit: str) -> str:
    digitos = "".join(c for c in str(cuit) if c.isdigit())
    if len(digitos) != 11:
        return str(cuit).strip()
    return f"{digitos[:2]}-{digitos[2:10]}-{digitos[10]}"


# convierte el SKU a mayúsculas y le saca los espacios (ej. "he-4110" queda "HE-4110")
def normalizar_sku(sku: str) -> str:
    return str(sku).strip().upper().replace(" ", "")


# lee catalogo.csv y lo devuelve como diccionario para buscar un producto por su código
# (lru_cache guarda el resultado para leer el CSV una sola vez)
@lru_cache(maxsize=1)
def leer_catalogo() -> dict[str, dict]:
    df = pd.read_csv(config.CSV_CATALOGO, encoding="utf-8-sig")
    return {normalizar_sku(fila["sku"]): fila for fila in df.to_dict(orient="records")}


# lee clientes.csv y lo devuelve como diccionario para buscar un cliente por su CUIT
@lru_cache(maxsize=1)
def leer_clientes() -> dict[str, dict]:
    df = pd.read_csv(config.CSV_CLIENTES, encoding="utf-8-sig")
    return {normalizar_cuit(fila["cuit"]): fila for fila in df.to_dict(orient="records")}


# arma una lista "SKU - nombre (marca)" con todos los productos
def listar_productos() -> str:
    return "\n".join(f"{sku} - {producto['nombre']} ({producto['marca']})" for sku, producto in leer_catalogo().items())