#!/usr/bin/env python3
"""
Hlasový kľúč – biometrické heslo pomocou hlasu
==============================================
Spustenie:   python app.py
             -> otvorí sa prehliadač s aplikáciou (http://127.0.0.1:8765)

Závislosti:  pip install numpy scipy
Mikrofón nahráva prehliadač, výpočty robí Python (voice_core.py).
"""

import base64
import json
import os
import socket
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

import voice_core as vc

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")
REC_DIR = os.path.join(HERE, "recordings")

LAST = {}            # posledný pokus pre každého používateľa (na prepočet pri zmene prísnosti)
LOCK = threading.Lock()


# ------------------------------------------------------------------ pomocné
def clean_user(u):
    u = "".join(ch for ch in str(u or "").strip() if ch.isalnum() or ch in "-_")
    return u[:32] or "pouzivatel"


def decode_audio(obj):
    pcm = np.frombuffer(base64.b64decode(obj["pcm"]), dtype=np.int16).astype(np.float64) / 32768
    return vc.resample(pcm, int(obj.get("sr", vc.SR)), vc.SR)


def save_recording(user, y, kind):
    try:
        p = os.path.join(REC_DIR, user, time.strftime("%Y%m%d_%H%M%S_") + kind + ".wav")
        vc.save_wav(p, y)
    except Exception:
        pass


def summary(f):
    return {"speech_sec": round(f["speech_sec"], 2), "f0": round(f["f0"], 1),
            "snr_db": round(f["snr_db"], 1)}


def result_json(r):
    v, t = r["values"], r["thresholds"]
    return {
        "ok": r["ok"],
        "checks": r["checks"],
        "values": {k: round(float(x), 4) for k, x in v.items()},
        "thresholds": {k: round(float(x), 4) for k, x in t.items()},
    }


def user_info(u):
    st = vc.template_status(u)
    info = {"name": u, "status": st}
    if st == "ok":
        tpl = vc.load_template(u)
        info["thresholds"] = {k: round(v, 3) for k, v in tpl["thresholds"].items()}
        info["f0"] = round(float(np.median([s["f0"] for s in tpl["samples"]])), 1)
        info["speech_sec"] = round(float(np.median([s["speech_sec"] for s in tpl["samples"]])), 2)
        info["created"] = time.strftime("%d.%m.%Y %H:%M",
                                        time.localtime(os.path.getmtime(vc.template_path(u))))
        info["warnings"] = tpl["warnings"]
    return info


# ------------------------------------------------------------------- API
def api(path, data):
    if path == "/api/users":
        return {"users": [user_info(u) for u in vc.list_users()]}

    if path == "/api/user":
        return user_info(clean_user(data.get("user")))

    if path == "/api/check":                       # kontrola kvality jednej vzorky
        u = clean_user(data.get("user"))
        y = decode_audio(data)
        f = vc.extract_features(y)
        save_recording(u, y, "enroll")
        return {"ok": True, "summary": summary(f)}

    if path == "/api/enroll":
        u = clean_user(data.get("user"))
        audios = [decode_audio(s) for s in data["samples"]]
        tpl = vc.build_template(u, audios)
        vc.save_template(tpl)
        with LOCK:
            LAST.pop(u, None)
        return {"ok": True, "user": user_info(u)}

    if path == "/api/verify":
        u = clean_user(data.get("user"))
        tpl = vc.load_template(u)
        if not tpl:
            raise ValueError("Používateľ nemá zaregistrované heslo.")
        y = decode_audio(data)
        save_recording(u, y, "verify")
        f = vc.extract_features(y)
        with LOCK:
            LAST[u] = f
        r = vc.verify_features(tpl, f, float(data.get("strictness", 1.0)))
        return {**result_json(r), "summary": summary(f)}

    if path == "/api/rescore":
        u = clean_user(data.get("user"))
        tpl = vc.load_template(u)
        with LOCK:
            f = LAST.get(u)
        if not (tpl and f):
            return {"none": True}
        return result_json(vc.verify_features(tpl, f, float(data.get("strictness", 1.0))))

    if path == "/api/delete":
        u = clean_user(data.get("user"))
        p = vc.template_path(u)
        if os.path.exists(p):
            os.remove(p)
        return {"ok": True}

    raise KeyError(path)


# ------------------------------------------------------------------ server
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            with open(os.path.join(WEB, "index.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if path.startswith("/api/"):
            return self.do_POST()
        self._send(404, {"error": "Nenájdené"})

    def do_POST(self):
        path = self.path.split("?")[0]
        n = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(n) or b"{}") if n else {}
            self._send(200, api(path, data))
        except KeyError:
            self._send(404, {"error": "Neznáma požiadavka"})
        except ValueError as e:
            self._send(400, {"error": str(e)})
        except Exception as e:                       # neočakávaná chyba
            self._send(500, {"error": f"{type(e).__name__}: {e}"})


def free_port(start=8765):
    for p in range(start, start + 50):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise RuntimeError("Nenašiel sa voľný port.")


def main():
    port = free_port()
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Hlasový kľúč beží na {url}  (ukončenie: Ctrl+C)")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nUkončené.")


if __name__ == "__main__":
    main()
