""" Arma el índice de los PDF de políticas (se corre una sola vez) """

import sys
from mesa_pedidos.indexado import indexar


if __name__ == "__main__":
    # forzar lo vuelve a armar aunque ya exista (ej. si cambian los PDF)
    indexar(forzar="--forzar" in sys.argv)
    print("Índice listo")