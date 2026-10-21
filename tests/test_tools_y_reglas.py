""" Prueba las 2 tools y las reglas comerciales con los CSV reales (sin LLM) """

from decimal import Decimal
import pytest
from mesa_pedidos.datos import leer_clientes
from mesa_pedidos.reglas import calcular_descuento_volumen, calcular_dias, evaluar_pedido, formatear_monto, validar_descuento
from mesa_pedidos.tools import consultar_producto, verificar_credito


def test_consultar_producto():
    producto = consultar_producto.invoke({"sku": "HE-4110", "cantidad": 60})
    assert producto["precio_lista"] == 289000
    assert producto["stock"] == 52
    assert producto["stock_suficiente"] is False


def test_consultar_producto_que_no_existe():
    producto = consultar_producto.invoke({"sku": "XX-0000"})
    assert producto["encontrado"] is False


def test_verificar_credito_con_cuit_sin_guiones():
    credito = verificar_credito.invoke({"cuit": "30709883417", "monto_pedido": 2000000})
    assert credito["credito_disponible"] == "1550000.00"
    assert credito["entra_en_limite"] is False


# art. 4: 5% desde $1.000.000, 8% desde $3.000.000 y 12% desde $6.000.000
def test_descuento_por_volumen():
    assert calcular_descuento_volumen(Decimal(999999)) == 0
    assert calcular_descuento_volumen(Decimal(1000000)) == 5
    assert calcular_descuento_volumen(Decimal(3000000)) == 8
    assert calcular_descuento_volumen(Decimal(6000000)) == 12


# pedido del MSG-009: 12% habitual + 5% por volumen = 17%
def test_monto_con_descuento_sin_errores_de_redondeo():
    cliente = leer_clientes()["30-71455982-2"]
    items = [{"sku": "AB-1020", "cantidad": 200}, {"sku": "AB-1120", "cantidad": 50}, {"sku": "ME-6030", "cantidad": 10}]
    validacion = evaluar_pedido(cliente, {"items": items, "forma_pago": "no_indicada"})
    assert validacion["montos"]["monto_con_descuento"] == Decimal("927940.00")


# art. 5: las herramientas eléctricas Dewalt tienen un tope de 15%
def test_tope_de_15_para_dewalt():
    cliente = leer_clientes()["30-69874512-2"]
    validacion = evaluar_pedido(cliente, {"items": [{"sku": "HE-4110", "cantidad": 4}], "forma_pago": "cuenta_corriente"})
    assert validacion["productos"][0]["descuento_aplicado"] == 15


# art. 5: pedir 19% en una Dewalt supera su tope y lo tiene que ver Gerencia
def test_pedir_mas_que_el_tope_pasa_a_gerencia():
    cliente = leer_clientes()["30-69874512-2"]
    pedido = {"items": [{"sku": "HE-4110", "cantidad": 4}], "forma_pago": "cuenta_corriente", "descuento_solicitado": 19}
    validacion = evaluar_pedido(cliente, pedido)
    assert validacion["decision"] == "humano"


# art. 6: el pago anticipado suma 3% de descuento
def test_descuento_financiero_por_pago_anticipado():
    cliente = leer_clientes()["20-31447856-9"]
    items = [{"sku": "SE-5025", "cantidad": 20}, {"sku": "ME-6030", "cantidad": 15}]
    contado = evaluar_pedido(cliente, {"items": items, "forma_pago": "contado"})
    anticipado = evaluar_pedido(cliente, {"items": items, "forma_pago": "anticipado"})
    monto_esperado = contado["montos"]["monto_con_descuento"] * Decimal("0.97")
    assert anticipado["montos"]["monto_con_descuento"] == monto_esperado.quantize(Decimal("0.01"))


# art. 7: con 30 a 60 días de mora el pedido lo ve Gerencia aunque pague anticipado
def test_mora_de_38_dias_pasa_a_gerencia():
    cliente = leer_clientes()["30-71099873-2"]
    validacion = evaluar_pedido(cliente, {"items": [{"sku": "ME-6030", "cantidad": 30}], "forma_pago": "anticipado"})
    assert validacion["decision"] == "humano"


# art. 7: un cliente suspendido solo puede comprar con pago anticipado
def test_cliente_suspendido():
    cliente = leer_clientes()["30-71788450-3"]
    for forma_pago in ("cuenta_corriente", "contado"):
        validacion = evaluar_pedido(cliente, {"items": [{"sku": "SE-5090", "cantidad": 2}], "forma_pago": forma_pago})
        assert validacion["decision"] == "rechazar"
    validacion = evaluar_pedido(cliente, {"items": [{"sku": "SE-5090", "cantidad": 2}], "forma_pago": "anticipado"})
    assert validacion["decision"] == "confirmar"


def test_producto_que_no_existe_se_deriva():
    cliente = leer_clientes()["30-71455982-2"]
    validacion = evaluar_pedido(cliente, {"items": [{"sku": "ZZ-9999", "cantidad": 1}], "forma_pago": "no_indicada"})
    assert validacion["decision"] == "derivar"


def test_descuento_de_gerencia_invalido():
    for descuento in (-5, 100, "abc"):
        with pytest.raises(ValueError):
            validar_descuento(descuento)


def test_formatear_monto():
    assert formatear_monto(Decimal("7450000")) == "$7.450.000"
    assert formatear_monto(Decimal("927940.5"), 2) == "$927.940,50"


# art. 2: el presupuesto vale 5 días hábiles (del jueves 10/09 al jueves 17/09)
def test_presupuesto_vencido():
    assert "venció el 2026-09-17" in calcular_dias("2026-09-10", "2026-09-20")


def test_presupuesto_vigente():
    assert "sigue vigente" in calcular_dias("2026-09-10", "2026-09-15")


def test_fecha_posterior_al_mensaje():
    assert "es posterior a la del mensaje" in calcular_dias("2026-09-25", "2026-09-20")