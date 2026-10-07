"""Cliente mínimo de Chrome DevTools Protocol (solo biblioteca estándar) para probar la app real.

Lanzar la app con:  set WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9223
Uso desde Python:
    import cdp
    side, dash = cdp.pagina("Barra lateral"), cdp.pagina("Dashboard")
    side.js("document.title")
    side.click_sel("#calc")             # clic sintético (no mueve el mouse real)
    dash.captura("dash.png")
"""
import base64
import json
import os
import socket
import struct
import time
import urllib.request

PUERTO = int(os.environ.get("CDP_PORT", "9223"))


class Pagina:
    def __init__(self, ws_url):
        host_port, path = ws_url[len("ws://"):].split("/", 1)
        host, port = host_port.split(":")
        self.sock = socket.create_connection((host, int(port)), timeout=120)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET /{path} HTTP/1.1\r\nHost: {host_port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            resp += self.sock.recv(4096)
        if b" 101 " not in resp.split(b"\r\n")[0]:
            raise RuntimeError(resp[:200])
        self.buf = resp.split(b"\r\n\r\n", 1)[1]
        self.n = 0

    # ---------------------------------------------------------------- websocket framing
    def _send(self, text):
        data = text.encode("utf-8")
        hdr = bytearray([0x81])
        ln = len(data)
        if ln < 126:
            hdr.append(0x80 | ln)
        elif ln < 65536:
            hdr.append(0x80 | 126); hdr += struct.pack(">H", ln)
        else:
            hdr.append(0x80 | 127); hdr += struct.pack(">Q", ln)
        mask = os.urandom(4)
        hdr += mask
        self.sock.sendall(bytes(hdr) + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(1 << 20)
            if not chunk:
                raise ConnectionError("cerrado")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _recv(self):
        parts = []
        while True:
            b0, b1 = self._read(2)
            ln = b1 & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", self._read(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(ln)
            op = b0 & 0x0F
            if op == 9:      # ping
                continue
            parts.append(payload)
            if b0 & 0x80:
                return b"".join(parts).decode("utf-8", "replace")

    # ---------------------------------------------------------------- CDP
    def call(self, method, **params):
        self.n += 1
        mid = self.n
        self._send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self._recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    def js(self, expr, await_promise=True):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=await_promise)
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"].get("exception", {}).get("description") or r["exceptionDetails"])
        return r.get("result", {}).get("value")

    def centro(self, selector):
        r = self.js(f"(()=>{{const e=document.querySelector({json.dumps(selector)});if(!e)return null;e.scrollIntoView({{block:'center'}});const b=e.getBoundingClientRect();return [b.left+b.width/2,b.top+b.height/2]}})()")
        if r is None:
            raise RuntimeError("no existe: " + selector)
        return r

    def mouse(self, tipo, x, y, button="left", clicks=1):
        self.call("Input.dispatchMouseEvent", type=tipo, x=x, y=y, button=button, clickCount=clicks,
                  buttons=1 if (tipo == "mousePressed" or (tipo == "mouseMoved" and button == "left_drag")) else 0)

    def click(self, x, y, button="left"):
        self.call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
        self.call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button=button, clickCount=1, buttons=1 if button == "left" else 2)
        self.call("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button=button, clickCount=1)

    def click_sel(self, selector, button="left"):
        x, y = self.centro(selector)
        self.click(x, y, button)
        return x, y

    def drag(self, x0, y0, x1, y1, pasos=12):
        self.call("Input.dispatchMouseEvent", type="mouseMoved", x=x0, y=y0)
        self.call("Input.dispatchMouseEvent", type="mousePressed", x=x0, y=y0, button="left", clickCount=1, buttons=1)
        for i in range(1, pasos + 1):
            self.call("Input.dispatchMouseEvent", type="mouseMoved", x=x0 + (x1 - x0) * i / pasos, y=y0 + (y1 - y0) * i / pasos, button="left", buttons=1)
            time.sleep(0.02)
        self.call("Input.dispatchMouseEvent", type="mouseReleased", x=x1, y=y1, button="left", clickCount=1)

    def tecla(self, key, code=None, vk=0, mods=0):
        for t in ("keyDown", "keyUp"):
            self.call("Input.dispatchKeyEvent", type=t, key=key, code=code or key, windowsVirtualKeyCode=vk, modifiers=mods)

    def escribir(self, texto):
        self.call("Input.insertText", text=texto)

    def captura(self, ruta):
        data = self.call("Page.captureScreenshot", format="png")["data"]
        with open(ruta, "wb") as f:
            f.write(base64.b64decode(data))
        return ruta

    def esperar(self, expr, timeout=60, intervalo=0.2):
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                if self.js(f"!!({expr})"):
                    return time.time() - t0
            except Exception:
                pass
            time.sleep(intervalo)
        raise TimeoutError(expr)


def paginas():
    with urllib.request.urlopen(f"http://127.0.0.1:{PUERTO}/json", timeout=5) as r:
        return json.loads(r.read().decode())


def pagina(titulo_contiene):
    for p in paginas():
        if p.get("type") == "page" and titulo_contiene in p.get("title", ""):
            return Pagina(p["webSocketDebuggerUrl"])
    raise RuntimeError("no encontrada: " + titulo_contiene)
