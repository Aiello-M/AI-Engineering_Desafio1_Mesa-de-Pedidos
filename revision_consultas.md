# Revisión manual de las 8 consultas

## MSG-001

Pregunta: Hola! Consulta: si les compro por 1.200.000 mas IVA, que descuento por volumen me corresponde? Y el flete me lo bonifican o lo tengo que pagar aparte?
Dato clave esperado: 5%, 1.500.000
Documento esperado: condiciones_comerciales_2026.pdf
Respuesta: Para un pedido de $1.200.000 más IVA, no corresponde descuento por volumen, ya que el monto neto del pedido está entre $250.000 y $999.999, lo que implica un 0% de descuento por volumen [condiciones_comerciales_2026.pdf, p. 1].

En cuanto al flete, Villa María, Córdoba, se encuentra en la zona 1, y el flete es bonificado al 100% solo cuando el monto neto del pedido supera los $1.500.000. Por lo tanto, en este caso, el flete no se bonifica y deberás pagarlo aparte [logistica_fletes_2026.pdf, p. 1].
¿Está bien?: No. Dice 0% pero 1.200.000 está en el rango de 1.000.000 a 2.999.999, que tiene 5%. También pone Villa María en zona 1 y es zona 2 (interior de Córdoba). Lo del flete sí está bien: no supera 1.500.000, así que no se bonifica.

## MSG-002

Pregunta: Buenos dias. Necesitamos saber cuanto tarda un envio a Neuquen capital y cuanto sale el flete, porque tenemos una parada de planta el mes que viene y queremos programar. Gracias.
Dato clave esperado: 175.000, 8
Documento esperado: logistica_fletes_2026.pdf
Respuesta: Buenos días. El envío a Neuquén capital pertenece a la Zona 5 (Patagonia), por lo que el flete es de $175.000 por envío y la entrega se realiza en un plazo de 8 a 12 días hábiles [logistica_fletes_2026.pdf, p. 1].
¿Está bien?: Sí.

## MSG-003

Pregunta: Che, compre 3 pares de zapatos de seguridad la semana pasada y me equivoque de talle. Los puedo devolver?
Dato clave esperado: no
Documento esperado: politica_devoluciones_2026.pdf
Respuesta: No se aceptan devoluciones por arrepentimiento de elementos de protección personal de uso individual, como los zapatos de seguridad, por razones de higiene. Por lo tanto, no podrás devolver los zapatos que compraste. [politica_devoluciones_2026.pdf, p. 1]
¿Está bien?: Sí. Usa la excepción de los zapatos de seguridad y no solo los 15 días.

## MSG-004

Pregunta: Estimados, el atornillador de impacto SKU HE-4330 viene con bateria incluida? Y si no viene, cual es el codigo de la bateria compatible?
Dato clave esperado: HE-4335
Documento esperado: fichas_tecnicas_2026.pdf
Respuesta: El atornillador de impacto SKU HE-4330 se vende sin batería ni cargador. La batería compatible es el SKU HE-4335 [fichas_tecnicas_2026.pdf, p. 1].
¿Está bien?: Sí.

## MSG-005

Pregunta: Buen dia, una pregunta: el presupuesto que me pasaron el 10 de septiembre sigue valiendo?
Dato clave esperado: 5
Documento esperado: condiciones_comerciales_2026.pdf
Respuesta: El presupuesto que se emitió el 10 de septiembre venció el 17 de septiembre, ya que mantiene el precio por 5 días hábiles y luego caduca automáticamente [condiciones_comerciales_2026.pdf, p. 1]. Por lo tanto, ya no es válido.
¿Está bien?: Sí. Dice que venció el 17/09, con el cálculo de días que hace Python.

## MSG-006

Pregunta: Hola, queriamos consultar por la garantia de las amoladoras. Compramos 6 hace 8 meses y una empezo a hacer ruido. Que cubre la garantia y como es el tramite?
Dato clave esperado: 12 meses
Documento esperado: politica_devoluciones_2026.pdf
Respuesta: La amoladora angular que compraron tiene una garantía de 12 meses por falla de fabricación, contados desde la fecha de factura [politica_devoluciones_2026.pdf, p. 1]. Sin embargo, la garantía no cubre el uso indebido, desgaste normal de piezas consumibles, ni daños por intervención de terceros no autorizados [politica_devoluciones_2026.pdf, p. 1].

Para iniciar el trámite, deben hacerlo dentro de los 10 días corridos desde la recepción de la mercadería, presentando el número de remito y una foto de la herramienta [politica_devoluciones_2026.pdf, p. 1]. Si ya pasaron esos 10 días, no podrán realizar el reclamo.

Si necesitan más información sobre el proceso o el estado de su reclamo, por favor indíquenme.
¿Está bien?: No del todo. Los 12 meses y lo que no cubre están bien, pero dice que hay 10 días para reclamar y ese plazo es para faltantes, errores de despacho o daños de transporte (punto 1), no para la garantía (punto 3). Así parece que el cliente ya no puede reclamar y sí puede. Tampoco dice que se gestiona en el service oficial de la marca.

## MSG-007

Pregunta: Cuantos aerosoles de WD-40 me pueden mandar a Santa Rosa? Habia escuchado que hay un limite por ser inflamable.
Dato clave esperado: 24
Documento esperado: logistica_fletes_2026.pdf
Respuesta: Para envíos a Santa Rosa, que está en la provincia de La Pampa, se permite un máximo de 24 unidades de aerosoles por envío, ya que se consideran carga peligrosa. Además, habrá un recargo del 15% sobre el flete por este tipo de mercadería. [logistica_fletes_2026.pdf, p. 1-2]
¿Está bien?: No. Dice máximo 24 aerosoles, pero La Pampa es zona 3 y el límite de 24 es solo para zonas 4 y 5. La medición lo da por bueno porque aparece el 24.

## MSG-008

Pregunta: Consulta administrativa: somos de Cordoba capital, nos corresponde percepcion de Ingresos Brutos en la factura? Nos aparecio en el ultimo remito y queriamos chequear.
Dato clave esperado: no
Documento esperado: condiciones_comerciales_2026.pdf
Respuesta: Como su empresa, Ferretería El Tornillo Feliz S.R.L., tiene domicilio fiscal en Córdoba, no les corresponde percepción de Ingresos Brutos en la factura. Los clientes inscriptos en Córdoba no sufren percepción de Ingresos Brutos [condiciones_comerciales_2026.pdf, p. 2].
¿Está bien?: Sí.

Resultado: 5 de 8 bien. La medición automática da 7 de 8 con el dato clave, porque en MSG-006 y MSG-007 el dato aparece aunque la respuesta tenga un error.
