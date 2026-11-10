"""Salida de consola en UTF-8, para que los scripts no se caigan en Windows.

Problema: en Windows, cuando la salida se redirige a un archivo (`> salida.txt`) o la consola
usa una página de códigos vieja (cp1252), Python codifica stdout con esa codificación. Al
imprimir caracteres que no existen en ella (→, ✓, ❌) lanza `UnicodeEncodeError` y el script
se corta a mitad de camino.

Solución: reconfigurar stdout/stderr a UTF-8 al arrancar cada punto de entrada.
`errors="replace"` es una red de seguridad: si algo no se puede escribir, se reemplaza por "?"
en vez de romper el programa.
"""

import sys


def use_utf8_output() -> None:
    """Fuerza UTF-8 en stdout y stderr. Llamarla al inicio de cada script ejecutable."""
    for stream in (sys.stdout, sys.stderr):
        # reconfigure existe en los streams de texto normales; si alguien reemplazó el stream
        # (por ejemplo un test que captura la salida), lo dejamos como está.
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
