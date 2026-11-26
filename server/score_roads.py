#!/usr/bin/env python3
"""Score every driver's road in an OpenStreetMap extract.

Usage:  python score_roads.py data/scotland-latest.osm.pbf data

Writes:
  data/roads.json   - rural A/B/minor road sections scored for bends and views
  data/limits.json  - every road with a speed limit tag, for the speedo's limit sign
"""
import json, math, sys, time
from collections import defaultdict

R = 6371000
ROAD_TYPES = {"trunk", "primary", "secondary", "tertiary", "unclassified"}
SECTION_MAX_M = 20000          # split long roads into sections of up to ~20 km
MIN_LEN_M, MIN_CURV, MIN_DENSITY = 2000, 250, 25


# ---------- geometry ----------
def dist(a, b):
    x = math.radians(b[1] - a[1]) * math.cos(math.radians((a[0] + b[0]) / 2))
    y = math.radians(b[0] - a[0])
    return math.hypot(x, y) * R


def path_len(g):
    return sum(dist(g[i - 1], g[i]) for i in range(1, len(g)))


def circ_r(a, b, c):
    A, B, C = dist(a, b), dist(b, c), dist(c, a)
    s = (A + B + C) / 2
    area = math.sqrt(max(0.0, s * (s - A) * (s - B) * (s - C)))
    return math.inf if area < 1e-6 else A * B * C / (4 * area)


def curvature(g):
    """After Adam Franco's 'curvature' project: distance spent in curves, weighted by tightness."""
    c = 0.0
    for i in range(1, len(g) - 1):
        r = circ_r(g[i - 1], g[i], g[i + 1])
        w = 2 if r < 30 else 1.6 if r < 60 else 1.3 if r < 100 else 1 if r < 175 else 0
        if w:
            c += dist(g[i - 1], g[i]) * w
    return c


def sample_every(g, step):
    out, acc = [g[0]], 0.0
    for i in range(1, len(g)):
        acc += dist(g[i - 1], g[i])
        if acc >= step:
            out.append(g[i]); acc = 0.0
    out.append(g[-1])
    return out


def split_sections(g, max_m):
    if path_len(g) <= max_m * 1.3:
        return [g]
    out, cur, acc = [], [g[0]], 0.0
    for i in range(1, len(g)):
        acc += dist(g[i - 1], g[i]); cur.append(g[i])
        if acc >= max_m and len(g) - i > 3:
            out.append(cur); cur, acc = [g[i]], 0.0
    if len(cur) > 1:
        if out and path_len(cur) < max_m * 0.3:
            out[-1].extend(cur[1:])
        else:
            out.append(cur)
    return out


# ---------- tags ----------
def parse_max(t):
    s, ty = t.get("maxspeed"), t.get("maxspeed:type") or ""
    if not s:
        if "nsl_single" in ty: return 60
        if "nsl_dual" in ty: return 70
        return None
    low = s.lower()
    if "nsl_single" in low or "national" in low: return 60
    if "nsl_dual" in low: return 70
    num = "".join(ch if ch.isdigit() else " " for ch in s).split()
    if not num: return None
    v = int(num[0])
    return v if "mph" in low else round(v * 0.621371)


def scenic_w(t):
    tour, nat, leis, land = t.get("tourism"), t.get("natural"), t.get("leisure"), t.get("landuse")
    if tour == "viewpoint": return 3
    if nat in ("coastline", "beach", "cliff", "water"): return 2
    if leis == "nature_reserve": return 1.5
    if nat == "peak": return 1.2
    if land == "forest" or nat == "wood": return 0.4
    return 0


# ---------- chaining + scoring ----------
def chain_ways(ways):
    groups = defaultdict(list)
    for w in ways:
        groups[w["ref"] or w["name"] or "#%d" % w["id"]].append(w)
    chains = []
    for key, lst in groups.items():
        ends = defaultdict(list)
        for i, w in enumerate(lst):
            ends[w["nodes"][0]].append(i); ends[w["nodes"][-1]].append(i)
        unused = set(range(len(lst)))
        while unused:
            i = unused.pop(); w = lst[i]
            nodes, g = list(w["nodes"]), list(w["g"])
            for side in ("tail", "head"):
                while True:
                    end = nodes[-1] if side == "tail" else nodes[0]
                    cand = next((j for j in ends[end] if j in unused), None)
                    if cand is None: break
                    unused.discard(cand)
                    vn, vg = lst[cand]["nodes"], lst[cand]["g"]
                    if side == "tail":
                        if vn[0] != end: vn, vg = vn[::-1], vg[::-1]
                        nodes += vn[1:]; g += vg[1:]
                    else:
                        if vn[-1] != end: vn, vg = vn[::-1], vg[::-1]
                        nodes = vn[:-1] + nodes; g = vg[:-1] + g
            chains.append({"name": w["name"], "ref": w["ref"], "g": g})
    return chains


def score_roads(ways, feats):
    grid = defaultdict(list)
    for i, (la, lo, w) in enumerate(feats):
        grid[(math.floor(la / 0.02), math.floor(lo / 0.03))].append((i, (la, lo), w))
    out = []
    for c in chain_ways(ways):
        for g in split_sections(c["g"], SECTION_MAX_M):
            ln = path_len(g)
            if ln < MIN_LEN_M: continue
            curv = curvature(g); dens = curv / (ln / 1000)
            if curv < MIN_CURV or dens < MIN_DENSITY: continue
            twist = min(10, 0.6 * min(10, math.sqrt(curv) / 5) + 0.4 * min(10, dens / 25))
            seen, total = set(), 0.0
            for p in sample_every(g, 400):
                ky, kx = math.floor(p[0] / 0.02), math.floor(p[1] / 0.03)
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        for fi, fp, fw in grid.get((ky + dy, kx + dx), ()):
                            if fi not in seen and dist(p, fp) < 1200:
                                seen.add(fi); total += fw
            scenic = min(10, 1.8 * math.sqrt(total))
            out.append({"name": c["name"], "ref": c["ref"], "len": round(ln), "curv": round(curv),
                        "twist": round(twist, 2), "scenic": round(scenic, 2),
                        "g": [[round(p[0], 5), round(p[1], 5)] for p in g]})
    return out


# ---------- reading the OSM file ----------
def read_osm(path):
    import osmium

    class Handler(osmium.SimpleHandler):
        def __init__(self):
            super().__init__()
            self.ways, self.feats, self.limits = [], [], []

        def node(self, n):
            w = scenic_w(n.tags)
            if w: self.feats.append((n.location.lat, n.location.lon, w))

        def way(self, w):
            t = w.tags
            hw = t.get("highway")
            sw = 0 if hw else scenic_w(t)
            if not hw and not sw: return
            try:
                g = [(nd.lat, nd.lon) for nd in w.nodes]
            except osmium.InvalidLocationError:
                return
            if len(g) < 2: return
            if sw:
                mid = g[len(g) // 2]
                self.feats.append((mid[0], mid[1], sw)); return
            mx = parse_max(t)
            if mx: self.limits.append([mx, [[round(p[0], 5), round(p[1], 5)] for p in g]])
            if hw not in ROAD_TYPES: return
            if t.get("junction") == "roundabout" or t.get("oneway") == "yes" or t.get("area") == "yes": return
            if t.get("lit") == "yes" or (mx and mx <= 30): return      # skip town roads
            self.ways.append({"id": w.id, "nodes": [nd.ref for nd in w.nodes], "g": g,
                              "name": t.get("name") or "", "ref": t.get("ref") or ""})

    h = Handler()
    h.apply_file(path, locations=True, idx="flex_mem")
    return h.ways, h.feats, h.limits


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src, outdir = sys.argv[1], sys.argv[2]
    t0 = time.time()
    print("Reading", src, "(a few minutes)...", flush=True)
    ways, feats, limits = read_osm(src)
    print(f"  {len(ways)} rural road pieces, {len(feats)} scenic features, {len(limits)} speed-limit roads", flush=True)
    print("Scoring...", flush=True)
    roads = score_roads(ways, feats)
    print(f"  {len(roads)} driver's road sections", flush=True)
    with open(f"{outdir}/roads.json", "w") as f: json.dump(roads, f, separators=(",", ":"))
    with open(f"{outdir}/limits.json", "w") as f: json.dump(limits, f, separators=(",", ":"))
    print(f"Done in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
