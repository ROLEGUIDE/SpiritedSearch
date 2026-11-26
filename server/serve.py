#!/usr/bin/env python3
"""Twisty home server: serves the app, the pre-scored roads, speed limits, and proxies routing to OSRM.

Run:  python serve.py            (listens on 127.0.0.1:8080; Tailscale Serve publishes it over https)
"""
import json, math, os, re, sys, urllib.request
from collections import defaultdict
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlsplit, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)                     # repo root, holds index.html
DATA = os.environ.get("TWISTY_DATA", os.path.join(HERE, "data"))
OSRM = os.environ.get("TWISTY_OSRM", "http://127.0.0.1:5000")
PORT = int(os.environ.get("TWISTY_PORT", "8080"))
R = 6371000


def dist(a, b):
    x = math.radians(b[1] - a[1]) * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot(x, math.radians(b[0] - a[0])) * R


def seg_dist(p, a, b):
    k = math.cos(math.radians(p[0]))
    ax, ay = (a[1] - p[1]) * k, a[0] - p[0]
    bx, by = (b[1] - p[1]) * k, b[0] - p[0]
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, -(ax * dx + ay * dy) / ((dx * dx + dy * dy) or 1)))
    return math.hypot(ax + t * dx, ay + t * dy) * math.radians(1) * R


print("Loading road data...", flush=True)
with open(os.path.join(DATA, "roads.json")) as f:
    ROADS = json.load(f)
for r in ROADS:
    g = r["g"]; step = max(1, len(g) // 12)
    r["_s"] = g[::step] + [g[-1]]
with open(os.path.join(DATA, "limits.json")) as f:
    LIMITS = json.load(f)
CELL = 0.01
LGRID = defaultdict(list)
for i, (mx, g) in enumerate(LIMITS):
    las = [p[0] for p in g]; los = [p[1] for p in g]
    for a in range(math.floor(min(las) / CELL), math.floor(max(las) / CELL) + 1):
        for b in range(math.floor(min(los) / CELL), math.floor(max(los) / CELL) + 1):
            LGRID[(a, b)].append(i)
print(f"Ready: {len(ROADS)} scored roads, {len(LIMITS)} speed-limit roads", flush=True)


def roads_near(lat, lon, km):
    c, lim = (lat, lon), km * 1000
    hits = [r for r in ROADS if any(dist(c, p) <= lim for p in r["_s"])]
    hits.sort(key=lambda r: r["twist"] + r["scenic"], reverse=True)
    return [{k: v for k, v in r.items() if k != "_s"} for r in hits[:400]]


def limit_at(lat, lon):
    p, best, bd = (lat, lon), None, 30.0
    a, b = math.floor(lat / CELL), math.floor(lon / CELL)
    cand = set()
    for da in (-1, 0, 1):
        for db in (-1, 0, 1):
            cand.update(LGRID.get((a + da, b + db), ()))
    for i in cand:
        mx, g = LIMITS[i]
        for j in range(1, len(g)):
            d = seg_dist(p, g[j - 1], g[j])
            if d < bd: bd, best = d, mx
    return best


class Handler(SimpleHTTPRequestHandler):
    def send_json(self, obj, code=200):
        body = json.dumps(obj, separators=(",", ":")).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        u = urlsplit(self.path)   # urlsplit keeps ';' in the path (OSRM uses it between points)
        if not u.path.startswith("/api/"):
            if u.path in ("/", "/index.html"):         # only the app page is served, nothing else from the folder
                self.path = "/index.html"
                return super().do_GET()
            return self.send_json({"error": "not found"}, 404)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/api/health":
                return self.send_json({"ok": True, "roads": len(ROADS)})
            if u.path == "/api/roads":
                km = min(60.0, max(1.0, float(q.get("r", 20))))
                return self.send_json(roads_near(float(q["lat"]), float(q["lon"]), km))
            if u.path == "/api/limit":
                return self.send_json({"max": limit_at(float(q["lat"]), float(q["lon"]))})
            if u.path.startswith("/api/route/"):
                coords = u.path[len("/api/route/"):]
                if not re.fullmatch(r"[0-9.,;\-]+", coords) or not re.fullmatch(r"[a-z_=&0-9]*", u.query):
                    return self.send_json({"code": "BadRequest"}, 400)
                with urllib.request.urlopen(f"{OSRM}/route/v1/driving/{coords}?{u.query}", timeout=20) as resp:
                    return self.send_json(json.loads(resp.read()))
            return self.send_json({"error": "not found"}, 404)
        except (KeyError, ValueError):
            return self.send_json({"error": "bad request"}, 400)
        except OSError as e:
            return self.send_json({"code": "RoutingDown", "error": str(e)}, 502)

    def log_message(self, fmt, *args):
        if "/api/" in (args[0] if args else ""):
            sys.stderr.write("%s\n" % (fmt % args))


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), partial(Handler, directory=APP_DIR))
    print(f"Twisty running at http://127.0.0.1:{PORT}  (Ctrl+C to stop)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
