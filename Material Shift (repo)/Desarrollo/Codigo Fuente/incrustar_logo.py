"""Incrusta Model\\recursos\\logo_128.png (base64) en Model\\app\\dashboard.html y sidebar.html,
para que el dashboard exportado (HTML suelto) muestre el logo sin archivos externos.
Se ejecuta desde compilar.ps1 después de crear_icono.py."""
import base64
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
uri = "data:image/png;base64," + base64.b64encode((RAIZ / "Model" / "recursos" / "logo_128.png").read_bytes()).decode()
for nombre in ("dashboard.html", "sidebar.html"):
    f = RAIZ / "Model" / "app" / nombre
    if not f.exists():
        continue
    t = f.read_text(encoding="utf-8")
    t2 = re.sub(r"const LOGO = '[^']*';", "const LOGO = '" + uri + "';", t)
    f.write_text(t2, encoding="utf-8")
    print(nombre, "ok" if t2 != t else "sin cambios")
