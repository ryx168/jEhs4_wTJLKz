"""XO Tours (新聯華假期) "about us" ad, built as Tesseract 3D scenes.

Reads xotours/script_timed.json (from tts.py) and writes xotours/project/project.tsrct.
Coordinates: X right, Y DOWN, Z into the screen; 1 m = 100 px. Lights are physical.
Six scenes:
  S1 hook   - fly through a corridor of real tour photos, "32 年" title
  S2 origin - 1994 Vancouver, one gold coin standing on a table (the tip)
  S3 name   - a lotus opens on dark water: 新聯華 = 心中有蓮花
  S4 reach  - gold-lined globe, routes grow from Vancouver to Toronto/LA/Taipei/Beijing
  S5 trips  - carousel of tour photos; 專業世界通 / 服務通世界
  S6 close  - a gold arch (the bridge) over water, then the logo end card
Env: TS (tsrct path), ONLY=S1,S3 to build a subset.
"""
import json, os, subprocess, sys, pathlib, math, shutil

HERE = pathlib.Path(__file__).resolve().parent
PROJ = HERE / "project"
WORK = PROJ / ".tesseract-work"
PREV = PROJ / "Previews"
ASSETS = HERE / "assets"
for d in (WORK, PREV, WORK / "batches"):
    d.mkdir(parents=True, exist_ok=True)
TS = os.environ.get("TS") or shutil.which("tsrct") or ""
if not TS:
    sys.exit("set TS to the tsrct executable")
DOC = PROJ / "project.tsrct"
W, H, FPS, PPM = 1920, 1080, 30, 100

timed = json.load(open(HERE / "script_timed.json", encoding="utf-8"))
SCENES = {s["id"]: s for s in timed["scenes"]}
LINES = {l["id"]: l for l in timed["lines"]}
TOTAL = timed["total"]
FONT = {"family": "Noto Sans CJK TC", "style": "Bold"}
FONT_REG = {"family": "Noto Sans CJK TC", "style": "Regular"}
FONT_SERIF = None   # set in main() when the serif TTC imports

GOLD = dict(base="#e8bd62", rough=0.26, metal=1.0)
TEAL = "#3c818c"

# ----------------------------------------------------------------- helpers
def run(*args, check=True):
    cmd = [TS] + [str(a) for a in args]
    print("$", " ".join(cmd[1:]), flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = r.stdout.strip()
    if out:
        print(out if len(out) < 2500 else out[:1200] + " ...")
    if r.stderr.strip():
        print(r.stderr.strip()[-3000:], file=sys.stderr)
    if check and r.returncode != 0:
        sys.exit(f"tsrct failed ({r.returncode})")
    return r

def srgb(hexstr, a=None):
    h = hexstr.lstrip("#")
    v = [int(h[i:i+2], 16) / 255 for i in (0, 2, 4)]
    return v + ([a] if a is not None else [])

def lin(hexstr):
    return [round(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4, 5) for c in srgb(hexstr)]

EASE = {"type": "cubicBezier", "x1": 0.3, "y1": 0, "x2": 0.2, "y2": 1}
EASE_IN = {"type": "cubicBezier", "x1": 0.6, "y1": 0, "x2": 0.9, "y2": 0.4}
EASE_OUT = {"type": "cubicBezier", "x1": 0.1, "y1": 0.5, "x2": 0.3, "y2": 1}
SMOOTH = {"type": "cubicBezier", "x1": 0.45, "y1": 0, "x2": 0.55, "y2": 1}
LIN = {"type": "linear"}

def euler(rot):
    rot = rot or (0, 0, 0)
    return {"type": "euler", "order": "XYZ", "orientation": [0, 0, 0],
            "rotationX": rot[0], "rotationY": rot[1], "rotationZ": rot[2]}

def tf3(pos, rot=None, scale=None):
    return {"anchorPoint": [0, 0, 0], "position": list(pos), "rotation": euler(rot),
            "scale": list(scale) if scale else [100, 100, 100]}

def aim_at(target, cid_a, cid_b):
    return {"relationships": {"constraints": [{"type": "aim", "id": cid_a,
            "target": {"id": cid_b, "target": {"type": "world"}, "offset": list(target), "offsetSpace": "local"},
            "up": [0, 1, 0], "upSpace": "world", "forwardAxis": "positiveZ", "influence": 1}]}}

def latlon(lat, lon, r):
    """Point on a sphere of radius r. North is -Y; lon 0 faces the camera at -Z; east is +X."""
    la, lo = math.radians(lat), math.radians(lon)
    return (r * math.cos(la) * math.sin(lo), -r * math.sin(la), -r * math.cos(la) * math.cos(lo))

def slerp(a, b, t):
    dot = max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b))))
    om = math.acos(dot)
    if om < 1e-6:
        return a
    s = math.sin(om)
    return tuple((math.sin((1 - t) * om) * x + math.sin(t * om) * y) / s for x, y in zip(a, b))

def unit(v):
    n = math.sqrt(sum(x * x for x in v))
    return tuple(x / n for x in v)

class Scene:
    """Collects the action batch for one Scene3D layer."""
    def __init__(self, sid, layer_id, id_base):
        self.sid, self.layer, self.nid, self.acts = sid, layer_id, id_base, []
        s = SCENES[sid]
        self.t0 = int(round(s["start"] * 1000))
        self.dur = int(round(s["dur"] * 1000))
        self.view_id, self.world_id, rs = self.id(), self.id(), self.id()
        self.acts.append({"type": "createFxScene3DLayer", "compositionId": "main", "layerId": layer_id,
            "name": f"{sid} scene", "pixelsPerMeter": PPM, "view": {"id": self.view_id, "exposure": 0},
            "activeRange": {"start": self.t0, "duration": self.dur},
            "transform": {"anchorPoint": [0, 0], "position": [0, 0], "scale": [100, 100], "rotation": 0, "opacity": 100},
            "world": {"id": self.world_id},
            "renderSettings": {"id": rs, "filmGate": None, "overscan": None, "lightGroups": [],
                               "lightCollections": [], "lightLinks": [], "outputs": [], "previewOutput": None}})

    def id(self):
        self.nid += 1
        return self.nid

    def at(self, line_id, plus=0.0):
        return int(round((LINES[line_id]["start"] - SCENES[self.sid]["start"] + plus) * 1000))

    def world(self, bg="#020203", ambient=0.03, ambient_color=(1, 1, 1)):
        self.acts.append({"type": "setFxScene3DWorld", "compositionId": "main", "layerId": self.layer, "world": {
            "id": self.world_id, "background": {"type": "color", "color": srgb(bg, 1)},
            "light": {"source": {"type": "color", "color": list(ambient_color) + [1]},
                      "intensity": ambient, "integration": "prefiltered"}}})  # "sampled" renders NaN in 0.6.0

    def camera(self, pos, aim, focal=35, exposure=0):
        cid = self.id()
        tr = {"position": list(pos), "rotation": euler(None)}
        tr.update(aim_at(aim, self.id(), self.id()))
        self.acts.append({"type": "addFxScene3DLayer", "compositionId": "main", "layerId": self.layer,
            "item": {"type": "Camera3D", "id": cid, "parentId": None, "name": "Camera", "isHidden": False,
                     "transform": tr,
                     "lens": {"type": "angle", "projection": {"type": "perspective",
                              "angleOfView": round(math.degrees(2 * math.atan(18 / focal)), 3)}},
                     "exposure": exposure}})
        self.acts.append({"type": "setFxScene3DActiveCamera", "compositionId": "main", "layerId": self.layer, "cameraItemId": cid})
        self.cam = cid
        return cid

    def light(self, kind, pos=None, aim=None, power=1000, color=(1, 1, 1), shadows=True, **extra):
        lid = self.id()
        tr = {"position": list(pos) if pos else [0, 0, 0], "rotation": euler(None)}
        if aim is not None:
            tr.update(aim_at(aim, self.id(), self.id()))
        if kind == "area":
            em = {"type": "area", "power": power, "shape": {"type": "rectangle", "areaSize": extra.pop("areaSize", [500, 500])}}
        else:
            em = {"type": kind, "power": power}
        em.update(extra)
        self.acts.append({"type": "addFxScene3DLayer", "compositionId": "main", "layerId": self.layer,
            "item": {"type": "Light3D", "id": lid, "parentId": None, "name": f"{kind} light", "isHidden": False,
                     "transform": tr, "emitter": em, "color": list(color) + [1], "castsShadows": shadows}})
        return lid

    @staticmethod
    def material(slot_id, bind_id, base="#808080", rough=0.5, metal=0.0, emissive=None, estrength=1.0,
                 unlit=False, tex=None, double=False):
        if tex:
            bc = {"type": "texture", "factor": [1, 1, 1], "sample": {
                "texture": {"source": {"type": "image", "assetId": tex}, "scale": [1, 1],
                            "wrapU": "clampToEdge", "wrapV": "clampToEdge",
                            "minFilter": "linear", "magFilter": "linear", "mipmaps": True},
                "interpretation": {"type": "color"}, "selection": {"type": "rgb"}}}
        else:
            bc = {"type": "constant", "value": lin(base)}
        inputs = {"baseColor": bc, "roughness": {"type": "constant", "value": rough},
                  "metallic": {"type": "constant", "value": metal}}
        if emissive:
            inputs["emissiveColor"] = {"type": "constant", "value": lin(emissive)}
            inputs["emissiveStrength"] = {"type": "constant", "value": estrength}
        b = {"id": bind_id, "inputs": inputs, "alphaMode": "opaque", "doubleSided": double, "unlit": unlit,
             "transmissionMedium": {"type": "sheet"}}
        return {"id": slot_id, "name": "Finish", "binding": b}

    def mesh(self, geometry, pos, mat, rot=None, scale=None, parent=None, name="Mesh", shadows=True):
        did, iid, sid, bid = self.id(), self.id(), self.id(), self.id()
        item = {"type": "Mesh3D", "id": iid, "parentId": parent, "name": name, "dataId": did, "packing": "whole",
                "isHidden": False, "transform": tf3(pos, rot, scale), "materialSlots": [self.material(sid, bid, **mat)],
                "regionSlots": [{"region": "primary", "slotId": sid}, {"region": "side", "slotId": sid}],
                "castsShadows": shadows, "receivesShadows": True}
        self.acts.append({"type": "addFxScene3DFragment", "compositionId": "main", "layerId": self.layer,
            "data": [{"type": "mesh", "id": did, "name": name + " geometry", "geometry": geometry,
                      "regions": [{"key": "primary", "name": "Primary"}, {"key": "side", "name": "Side"}]}],
            "items": [item]})
        return iid, bid

    def text3d(self, text, pos, size=200, depth=40, mat=None, side_mat=None, bevel=0, rot=None, name="Text",
               parent=None, font=None):
        font = font or FONT
        did, iid = self.id(), self.id()
        mat = mat or {}
        s1, b1, s2, b2 = self.id(), self.id(), self.id(), self.id()
        data = {"type": "text", "id": did, "name": name + " geometry", "text": text, "fontFamily": font["family"],
                "fontStyle": font["style"], "fontSize": size, "depth": depth, "justification": "center", "tracking": 0,
                "regions": [{"key": "front", "name": "Front"}, {"key": "back", "name": "Back"}, {"key": "side", "name": "Side"}]}
        if bevel:
            data["bevelSize"], data["bevelSegments"] = bevel, 3
        item = {"type": "Text3D", "id": iid, "parentId": parent, "name": name, "dataId": did, "isHidden": False,
                "transform": tf3(pos, rot),
                "materialSlots": [self.material(s1, b1, **mat), self.material(s2, b2, **(side_mat or mat))],
                "regionSlots": [{"region": "front", "slotId": s1}, {"region": "back", "slotId": s1}, {"region": "side", "slotId": s2}],
                "castsShadows": True, "receivesShadows": True}
        self.acts.append({"type": "addFxScene3DFragment", "compositionId": "main", "layerId": self.layer,
                          "data": [data], "items": [item]})
        return iid, b1

    def group(self, pos=(0, 0, 0), rot=None, name="Group", parent=None, scale=None):
        gid = self.id()
        self.acts.append({"type": "addFxScene3DFragment", "compositionId": "main", "layerId": self.layer, "data": [],
            "items": [{"type": "Group3D", "id": gid, "parentId": parent, "name": name, "isHidden": False,
                       "transform": tf3(pos, rot, scale)}]})
        return gid

    def card(self, photo, pos, rot=None, w=640, h=400, name="Card", parent=None, back=None):
        """A tour photo on an unlit plane in a thin gold frame; `back` puts a photo on the reverse too."""
        g = self.group(pos, rot, name=name, parent=parent)
        self.mesh({"type": "box", "size": [w + 24, h + 24, 8]}, (0, 0, 8), GOLD, parent=g, name=name + " frame")
        self.mesh({"type": "plane", "size": [w, h]}, (0, 0, 0),
                  dict(base="#ffffff", rough=0.6, unlit=True, tex=photo, double=True), parent=g, name=name + " photo",
                  shadows=False)
        if back:
            self.mesh({"type": "plane", "size": [w, h]}, (0, 0, 16), dict(base="#ffffff", rough=0.6, unlit=True, tex=back,
                      double=True), rot=(0, 180, 0), parent=g, name=name + " back", shadows=False)
        return g

    def anim(self, item, prop, keys, kind="float"):
        """keys: list of (ms, value, easing)."""
        kf = [{"id": f"{self.sid}-{item}-{prop}-{n}", "layerTime": int(max(0, min(self.dur, t))),
               "value": {"type": kind, "value": (list(v) if kind != "float" else v)}, "easing": e}
              for n, (t, v, e) in enumerate(keys)]
        self.acts.append({"type": "setFxAnimator", "compositionId": "main",
            "target": {"type": "styleProperty", "layerId": self.layer, "itemId": item, "propertyName": prop},
            "animator": {"type": "keyframes", "enabled": True, "keyframes": kf}, "dependencies": [], "layerRefBindings": []})

    def path(self, item, points, t_from, t_to, ease=LIN):
        """position keyframes spread evenly over [t_from, t_to] (ms)."""
        n = len(points) - 1
        self.anim(item, "position", [(t_from + (t_to - t_from) * k / n, p, ease) for k, p in enumerate(points)], "vector3")

    def fade(self, t_in=1000, t_out=1000, start=-9, extra=None):
        """Exposure: start -> 0 -> (extra keys) -> black."""
        d = self.dur
        hold = extra[-1][1] if extra else 0
        keys = [(0, start, LIN), (t_in, 0, EASE_OUT)] + (extra or []) + [(d - t_out, hold, LIN), (d - 40, -9, EASE_IN)]
        self.anim(self.view_id, "exposure", keys)

    def dump(self):
        p = WORK / "batches" / f"{self.sid}.json"
        json.dump(self.acts, open(p, "w", encoding="utf-8"), ensure_ascii=False)
        return p

# ----------------------------------------------------------------- 2D overlays
OVERLAYS = []
_layer_ids = iter(range(100, 400))
_key_n = [0]

def _fade_keys(lid, d, fade):
    _key_n[0] += 1
    k = _key_n[0]
    OVERLAYS.append({"type": "setFxPropertyKeyframes", "compositionId": "main",
        "property": {"layerId": lid, "propertyType": "opacity"},
        "keyframes": [
            {"id": f"ov{k}-a", "layerTime": 0, "value": {"type": "float", "value": 0}, "easing": LIN},
            {"id": f"ov{k}-b", "layerTime": fade, "value": {"type": "float", "value": 100}, "easing": EASE_OUT},
            {"id": f"ov{k}-c", "layerTime": d - fade, "value": {"type": "float", "value": 100}, "easing": LIN},
            {"id": f"ov{k}-d", "layerTime": d, "value": {"type": "float", "value": 0}, "easing": EASE_IN}]})

def text2d(text, x, y, t_start, t_end, size=44, color="#ffffff", align="left", box_w=None, font=None,
           fade=400, tracking=0, stroke=None):
    lid = next(_layer_ids)
    f = font or FONT
    st = {"text": text, "fontFamily": f["family"], "fontStyle": f["style"], "fontSize": size,
          "fillColor": srgb(color, 1), "justification": align, "strokeWidth": 0, "tracking": tracking}
    if stroke:
        st.update({"strokeEnabled": True, "strokeWidth": stroke[1], "strokeColor": srgb(stroke[0], 1)})
    if box_w:
        st.update({"boxText": True, "boxPosition": [0, 0], "boxSize": [box_w, int(size * 1.7)]})
    s, e = int(t_start * 1000), int(t_end * 1000)
    d = max(e - s, 200)
    OVERLAYS.append({"type": "createFxTextLayer", "compositionId": "main", "insertIndex": 0, "layerId": lid,
        "name": text[:24], "activeRange": {"start": s, "duration": d},
        "transform": {"anchorPoint": [0, 0], "position": [x, y], "scale": [100, 100], "rotation": 0, "opacity": 100},
        "sourceText": st})
    if fade and d > 3 * fade:
        _fade_keys(lid, d, fade)
    return lid

def centered(text, y, t0, t1, size=60, color="#ffffff", font=None, fade=450, tracking=0, stroke=None):
    return text2d(text, 0, y, t0, t1, size=size, color=color, align="center", box_w=W, font=font, fade=fade,
                  tracking=tracking, stroke=stroke)

def image2d(asset, x, y, w, h, t_start, t_end, scale=100, fade=500):
    lid = next(_layer_ids)
    s, e = int(t_start * 1000), int(t_end * 1000)
    d = max(e - s, 200)
    OVERLAYS.append({"type": "createFxImageLayer", "compositionId": "main", "insertIndex": 0, "layerId": lid,
        "name": asset, "activeRange": {"start": s, "duration": d},
        "transform": {"anchorPoint": [w / 2, h / 2], "position": [x, y], "scale": [scale, scale], "rotation": 0, "opacity": 100},
        "source": {"assetId": asset}})
    if fade and d > 3 * fade:
        _fade_keys(lid, d, fade)
    return lid

def win(line_id, lead=0.0, tail=0.6):
    l = LINES[line_id]
    return l["start"] + lead, l["start"] + l["dur"] + tail

def sc_end(sid, minus=0.3):
    return SCENES[sid]["end"] - minus

PHOTOS = ["cruise", "london", "barcelona", "copenhagen", "kanas", "rome", "malta", "cornwall", "vatican", "dublin"]

# ----------------------------------------------------------------- scenes
def scene_S1():
    """Hook: fly through a corridor of real tour photos."""
    s = Scene("S1", 10, 1000)
    s.world("#050b14", 0.05, (0.7, 0.8, 1))
    s.mesh({"type": "box", "size": [6000, 20, 16000]}, (0, 420, 5000), dict(base="#0a121c", rough=0.12), name="Floor")
    for i, p in enumerate(PHOTOS):
        ang = math.radians(i * 137.5 + 20)
        x, y = 760 * math.cos(ang), 300 * math.sin(ang) - 40
        z = 900 + i * 820
        s.card(p, (x, y, z), rot=(0, -28 if x > 0 else 28, 0), name=f"Card {p}")
    for z in (1500, 4500, 7500):
        s.light("point", pos=(0, -600, z), power=60000, color=(1, 0.86, 0.66), sourceRadius=40)
    s.light("area", pos=(0, -2500, -1500), aim=(0, 0, 3000), power=120000, color=(0.8, 0.9, 1), areaSize=[2000, 2000])
    cam = s.camera((0, -60, -1400), (0, -60, 30000), focal=28)
    s.path(cam, [(0, -60, -1400), (0, -90, 3200), (0, -120, 7600)], 0, s.dur, LIN)
    s.fade(250, 500, start=-3)
    a = SCENES["S1"]["start"] + 0.25
    centered("32 年，帶華人看世界", 400, a, sc_end("S1", 0.2), size=104, font=FONT_SERIF or FONT, stroke=("#0a1420", 5))
    centered("新聯華假期  XO TOURS  ·  1994 – 2026", 560, a + 0.6, sc_end("S1", 0.2), size=40, color="#f0d79a", tracking=60)
    return s

def scene_S2():
    """1994, Vancouver: one coin on a table - the tip that started a company."""
    s = Scene("S2", 11, 2000)
    s.world("#040304", 0.02, (1, 0.9, 0.8))
    s.mesh({"type": "box", "size": [8000, 60, 6000]}, (0, 30, 1000), dict(base="#2e1d12", rough=0.35), name="Table")
    coin, coinb = s.mesh({"type": "cylinder", "radius": 70, "height": 14}, (0, -70, 0),
                         dict(GOLD, rough=0.18, emissive="#ffcf6b", estrength=0.0), rot=(90, 0, 0), name="Coin")
    s.anim(coin, "rotationY", [(0, -30, LIN), (s.dur, 330, LIN)])
    t_kind = s.at("s2b", 0.2)
    s.anim(coinb, "emissiveStrength", [(0, 0, LIN), (t_kind, 0, LIN), (t_kind + 2500, 2.5, EASE_OUT)])
    s.text3d("1994", (0, -170, 2600), size=520, depth=80, mat=dict(base="#2a5d66", rough=0.5, metal=0.3),
             side_mat=dict(base="#173a40", rough=0.5, metal=0.3), bevel=6, name="1994", font=FONT_SERIF or FONT)
    key = s.light("spot", pos=(300, -1600, -500), aim=(0, -70, 0), power=7000, color=(1, 0.82, 0.6), coneAngle=26, coneFeather=0.7)
    s.anim(key, "power", [(0, 7000, LIN), (t_kind, 7000, LIN), (t_kind + 2500, 15000, EASE)])
    s.light("area", pos=(-200, -350, -900), aim=(0, -70, 0), power=2500, color=(1, 0.9, 0.75), areaSize=[400, 300], shadows=False)
    s.light("spot", pos=(-1800, -1400, 600), aim=(0, -300, 2600), power=900, color=(0.55, 0.8, 1), coneAngle=30, coneFeather=0.6)
    cam = s.camera((-160, -95, -520), (0, -110, 0), focal=50)
    s.path(cam, [(-160, -95, -520), (-40, -160, -1300), (100, -230, -2200)], 0, s.dur, SMOOTH)
    s.fade(900, 700)
    a, b = win("s2a", 0.1, 1.0)
    text2d("1994  ·  溫哥華  Vancouver", 120, 930, a, b, size=48, color="#f0d79a", tracking=40)
    a, b = win("s2b", 0.2, 1.2)
    centered("一份善意，成了一家旅行社的起點", 900, a, b, size=52, font=FONT_SERIF or FONT)
    return s

def scene_S3():
    """新聯華 = 心中有蓮花: a lotus opens on dark water and lights from within."""
    s = Scene("S3", 12, 3000)
    s.world("#03080c", 0.03, (0.6, 0.85, 1))
    s.mesh({"type": "box", "size": [40000, 20, 40000]}, (0, 12, 0), dict(base="#04141a", rough=0.14), name="Water")
    for x, z, r in ((-700, 300, 260), (650, 500, 220), (-300, 1200, 300), (900, -350, 180)):
        s.mesh({"type": "cylinder", "radius": r, "height": 6}, (x, -1, z), dict(base="#2f6b4a", rough=0.55), name="Pad")
    t_open = s.at("s3a", 0.0)
    t_full = s.at("s3a", 3.5)
    rings = [  # count, hinge radius, closed tilt, open tilt, yaw offset, colour, scale %
        (6, 18, 84, 60, 0, "#fbe8ee", (30, 9, 85)),
        (8, 34, 80, 38, 22.5, "#f7d2dd", (34, 9, 100)),
        (12, 48, 70, 14, 15, "#f0bccb", (36, 9, 110)),
    ]
    for count, r0, closed, opened, off, col, sc in rings:
        for k in range(count):
            yaw = s.group((0, -40, 0), rot=(0, off + k * 360 / count, 0), name="Petal yaw")
            hinge = s.group((0, 0, r0), rot=(closed, 0, 0), name="Petal hinge", parent=yaw)
            s.mesh({"type": "sphere", "radius": 100}, (0, 0, sc[2]), dict(base=col, rough=0.45, emissive="#ffb7c8", estrength=0.15),
                   scale=sc, parent=hinge, name="Petal")
            s.anim(hinge, "rotationX", [(0, closed, LIN), (t_open, closed, LIN), (t_full + k * 60, opened, EASE)])
    heart, heartb = s.mesh({"type": "sphere", "radius": 34}, (0, -70, 0), dict(GOLD, emissive="#ffd27a", estrength=0.0), name="Heart")
    s.anim(heartb, "emissiveStrength", [(0, 0, LIN), (t_open + 800, 0, LIN), (t_full + 600, 6, EASE_OUT)])
    glow = s.light("point", pos=(0, -120, 0), power=10, color=(1, 0.8, 0.5), sourceRadius=20)
    s.anim(glow, "power", [(0, 10, LIN), (t_open + 800, 10, LIN), (t_full + 600, 9000, EASE_OUT)])
    s.light("area", pos=(-1200, -1800, -1400), aim=(0, -60, 0), power=70000, color=(1, 0.88, 0.8), areaSize=[1200, 1200])
    s.light("spot", pos=(900, -900, 1600), aim=(0, -80, 0), power=9000, color=(0.5, 0.85, 1), coneAngle=35, coneFeather=0.5)
    cam = s.camera((-300, -520, -1500), (0, -90, 0), focal=40)
    s.path(cam, [(-300, -520, -1500), (300, -420, -1250), (700, -330, -900), (620, -280, -700)], 0, s.dur, LIN)
    s.fade(900, 800)
    a, b = win("s3a", 0.3, 1.4)
    centered("新聯華  ＝  心中有蓮花", 860, a, b, size=64, font=FONT_SERIF or FONT, color="#fff3e0")
    a, b = win("s3b", 0.2, 1.0)
    centered("真心  ·  誠心  ·  奉獻心", 860, a, b, size=56, color="#f0d79a", tracking=80)
    return s

CITIES = [  # name, lat, lon, fraction of line s4a at which it is spoken
    ("多倫多 Toronto", 43.65, -79.38, 0.42),
    ("洛杉磯 Los Angeles", 34.05, -118.24, 0.58),
    ("台北 Taipei", 25.03, 121.56, 0.74),
    ("北京 Beijing", 39.90, 116.40, 0.86),
]
VAN = (49.28, -123.12)

def scene_S4():
    """From Vancouver to four branch cities: gold routes grow over a globe."""
    s = Scene("S4", 13, 4000)
    s.world("#02050b", 0.04, (0.6, 0.75, 1))
    R = 800
    s.mesh({"type": "sphere", "radius": R}, (0, 0, 0), dict(base="#0e2846", rough=0.62, metal=0.05), name="Globe")
    line = dict(base="#000000", rough=0.5, emissive="#d9b25a", estrength=1.3)
    for lat in (-60, -30, 0, 30, 60):
        s.mesh({"type": "torus", "radius": R * math.cos(math.radians(lat)) + 2, "tubeRadius": 2.2},
               (0, -R * math.sin(math.radians(lat)), 0), line, name=f"Lat {lat}", shadows=False)
    for lon in range(0, 180, 30):
        g = s.group((0, 0, 0), rot=(0, lon, 0), name=f"Meridian {lon}")
        s.mesh({"type": "torus", "radius": R + 2, "tubeRadius": 2.2}, (0, 0, 0), line, rot=(90, 0, 0), parent=g,
               name=f"Lon {lon}", shadows=False)
    pin = dict(base="#000000", rough=0.5, emissive="#8ff4ff", estrength=5)
    s.mesh({"type": "sphere", "radius": 24}, latlon(*VAN, R + 6), dict(pin, emissive="#ffe08a", estrength=8), name="Vancouver")
    l0 = LINES["s4a"]
    t_line0 = s.at("s4a", 0.0)
    a_van = unit(latlon(*VAN, 1))
    for name, la, lo, frac in CITIES:
        t_arrive = t_line0 + int(l0["dur"] * frac * 1000)
        t_start = t_arrive - 1400
        b = unit(latlon(la, lo, 1))
        ang = math.acos(max(-1, min(1, sum(x * y for x, y in zip(a_van, b)))))
        n = 30
        for k in range(1, n + 1):
            t = k / n
            p = slerp(a_van, b, t)
            alt = R * (1.01 + 0.10 * ang * math.sin(math.pi * t))
            did, _ = s.mesh({"type": "sphere", "radius": 6}, tuple(x * alt for x in p),
                            dict(base="#000000", rough=0.5, emissive="#ffd27a", estrength=4), scale=(1, 1, 1),
                            name="Route dot", shadows=False)
            tk = t_start + int(1400 * t)
            s.anim(did, "scale", [(0, (1, 1, 1), LIN), (tk, (1, 1, 1), LIN), (tk + 250, (100, 100, 100), EASE_OUT)], "vector3")
        cid, _ = s.mesh({"type": "sphere", "radius": 16}, latlon(la, lo, R + 6), pin, scale=(1, 1, 1), name=name)
        s.anim(cid, "scale", [(0, (1, 1, 1), LIN), (t_arrive, (1, 1, 1), LIN), (t_arrive + 350, (130, 130, 130), EASE_OUT)], "vector3")
    s.light("area", pos=(-3000, -2500, -2500), aim=(0, 0, 0), power=70000, color=(1, 0.92, 0.82), areaSize=[2500, 2500])
    s.light("area", pos=(2500, 1200, 2500), aim=(0, 0, 0), power=40000, color=(0.4, 0.6, 1), areaSize=[1500, 1500])
    # orbit: North America -> over the Pacific -> East Asia
    D = 2700
    v0, v1 = unit(latlon(42, -100, 1)), unit(latlon(32, 128, 1))
    mid = unit(latlon(46, -175, 1))
    pts = [tuple(x * D for x in slerp(v0, mid, k / 6)) for k in range(7)] + \
          [tuple(x * D for x in slerp(mid, v1, k / 6)) for k in range(1, 7)]
    cam = s.camera(pts[0], (0, 0, 0), focal=35)
    s.path(cam, pts, 0, s.dur, LIN)
    s.fade(800, 800)
    t_abs0 = l0["start"]
    text2d("溫哥華 Vancouver", 120, 140, t_abs0, sc_end("S4"), size=46, color="#ffe08a")
    for k, (name, la, lo, frac) in enumerate(CITIES):
        ta = t_abs0 + l0["dur"] * frac
        text2d("→ " + name, 120, 210 + k * 62, ta, sc_end("S4"), size=40, color="#bff7ff", font=FONT_REG)
    a, b = win("s4b", 0.2, 1.0)
    centered("百餘家同業旅行社的機票調度中心", 930, a, b, size=48, color="#ffffff", stroke=("#0a1420", 4))
    return s

def scene_S5():
    """The trips: a carousel of tour photos turning around a lit centre."""
    s = Scene("S5", 14, 5000)
    s.world("#03060a", 0.04, (0.8, 0.85, 1))
    s.mesh({"type": "box", "size": [30000, 20, 30000]}, (0, 10, 0), dict(base="#0b1118", rough=0.08), name="Floor")
    s.mesh({"type": "torus", "radius": 1650, "tubeRadius": 6}, (0, -2, 0),
           dict(base="#000000", rough=0.5, emissive="#d9b25a", estrength=2), name="Ring", shadows=False)
    R = 1500
    ph = PHOTOS[:8]
    for k, p in enumerate(ph):
        th = k * 360 / len(ph)
        r = math.radians(th)
        s.card(p, (R * math.sin(r), -330, -R * math.cos(r)), rot=(0, -th, 0), name=f"Card {p}",
               back=ph[(k + 4) % len(ph)])
    core, coreb = s.mesh({"type": "sphere", "radius": 140}, (0, -330, 0), dict(GOLD, emissive="#ffd27a", estrength=0.6), name="Core")
    t_slogan = s.at("s5b", 0.0)
    s.anim(coreb, "emissiveStrength", [(0, 0.6, LIN), (t_slogan, 0.6, LIN), (t_slogan + 2000, 5, EASE_OUT)])
    s.light("point", pos=(0, -900, 0), power=60000, color=(1, 0.85, 0.65), sourceRadius=60)
    s.light("area", pos=(0, -3500, -3500), aim=(0, -300, 0), power=150000, color=(0.85, 0.9, 1), areaSize=[2500, 2500])
    D, Y = 3400, -620
    pts = [(D * math.sin(math.radians(a)), Y + 140 * math.sin(math.radians(a * 2)), -D * math.cos(math.radians(a)))
           for a in range(-20, 200, 20)]
    cam = s.camera(pts[0], (0, -620, 0), focal=30)
    s.path(cam, pts, 0, s.dur, LIN)
    s.fade(800, 800)
    a, b = win("s5a", 0.1, 0.9)
    centered("郵輪  ·  歐洲  ·  北歐  ·  地中海  ·  絲綢之路", 930, a, b, size=46, color="#ffffff", tracking=20)
    a, b = win("s5b", 0.1, 1.6)
    centered("專業  ─  世界通", 90, a, b, size=84, font=FONT_SERIF or FONT, color="#f6dc9a", stroke=("#0a1420", 3))
    centered("服務  ─  通世界", 200, a + 1.6, b, size=84, font=FONT_SERIF or FONT, color="#f6dc9a", stroke=("#0a1420", 3))
    return s

def scene_S6():
    """The bridge: a gold arch over still water at dawn, then the end card."""
    s = Scene("S6", 15, 6000)
    s.world("#0a0d16", 0.05, (1, 0.85, 0.7))
    s.mesh({"type": "box", "size": [40000, 20, 40000]}, (0, 10, 0), dict(base="#07151d", rough=0.04), name="Water")
    arch, archb = s.mesh({"type": "torus", "radius": 1300, "tubeRadius": 30}, (0, 0, 1200),
                         dict(GOLD, emissive="#ffcf70", estrength=0.0), rot=(90, 0, 0), name="Bridge")
    t_a = s.at("s6a", 0.0)
    t_card = s.at("s6b", -0.4)
    s.anim(archb, "emissiveStrength", [(0, 0, LIN), (t_a, 0, LIN), (t_a + 2600, 3.5, EASE_OUT),
                                       (t_card, 3.5, LIN), (t_card + 1500, 0.8, EASE)])
    sun, sunb = s.mesh({"type": "sphere", "radius": 700}, (0, -150, 9000),
                       dict(base="#000000", rough=0.5, emissive="#ffb35c", estrength=1.0), name="Sun", shadows=False)
    s.anim(sunb, "emissiveStrength", [(0, 1.0, LIN), (t_a, 1.0, LIN), (t_a + 3000, 4.0, EASE)])
    # rises behind the arch, then sets again under the end card so the text never sits on it
    t_set = s.at("s6b", -0.4)
    s.anim(sun, "position", [(0, (0, 250, 9000), LIN), (t_set, (0, -120, 9000), EASE_OUT),
                             (t_set + 2200, (0, 900, 9000), EASE)], "vector3")
    warm = s.light("spot", pos=(0, -900, 7000), aim=(0, -300, 1200), power=60000, color=(1, 0.72, 0.45), coneAngle=40, coneFeather=0.6)
    s.anim(warm, "power", [(0, 60000, LIN), (t_a, 60000, LIN), (t_a + 3000, 220000, EASE),
                           (t_card, 220000, LIN), (t_card + 2000, 40000, EASE)])
    s.light("area", pos=(-2500, -2500, -2500), aim=(0, -400, 1200), power=60000, color=(0.6, 0.75, 1), areaSize=[1500, 1500])
    cam = s.camera((0, -160, -3600), (0, -520, 1200), focal=32)
    s.path(cam, [(0, -160, -3600), (0, -240, -2900)], 0, s.dur, SMOOTH)
    t_end = s.at("s6b", -0.4)
    s.fade(900, 700, extra=[(t_end, 0, LIN), (t_end + 900, -2.6, EASE)])
    a, _ = win("s6a", 0.2, 0)
    centered("用旅遊，搭起世界和平的橋樑", 80, a, LINES["s6b"]["start"] - 0.3, size=72, font=FONT_SERIF or FONT,
             color="#fff3e0", stroke=("#0a1420", 2))
    e0 = LINES["s6b"]["start"] - 0.1
    e1 = TOTAL - 0.15
    image2d("logo", 960, 360, 344, 356, e0, e1, scale=78)
    centered("新聯華假期   XO TOURS", 560, e0 + 0.3, e1, size=72, font=FONT_SERIF or FONT, color="#f6dc9a", tracking=40, stroke=("#0a1420", 4))
    centered("1994 – 2026  ·  32 週年", 668, e0 + 0.6, e1, size=38, color="#d8e6ea", tracking=60, stroke=("#0a1420", 3))
    centered("xotours.net   ·   1.800.978.1788", 760, e0 + 0.9, e1, size=46, color="#ffffff", tracking=30, stroke=("#0a1420", 4))
    return s

# ----------------------------------------------------------------- document
def find_layers(node, path="doc"):
    if isinstance(node, dict):
        if isinstance(node.get("layers"), list):
            return node, path
        for k, v in node.items():
            r = find_layers(v, f"{path}.{k}")
            if r:
                return r
    elif isinstance(node, list):
        for i, v in enumerate(node):
            r = find_layers(v, f"{path}[{i}]")
            if r:
                return r
    return None

def set_key(node, key, value, count=[0]):
    if isinstance(node, dict):
        for k, v in list(node.items()):
            if k == key and (not isinstance(v, (dict, list)) or (isinstance(v, dict) and set(v) >= {"width", "height"})):
                node[k] = value; count[0] += 1
            else:
                set_key(v, key, value, count)
    elif isinstance(node, list):
        for v in node:
            set_key(v, key, value, count)
    return count[0]

def import_font(path, want):
    if not os.path.exists(path):
        print("font missing:", path)
        return None
    r = run("project", "import-font", "--project", DOC, "--file", path, check=False)
    try:
        info = json.loads(r.stdout)
    except Exception:
        return None
    faces = info.get("faces") or [info]
    pick = next((f for f in faces if want in str(f.get("fontFamily", ""))), None)
    if pick and "fontFamily" in pick and "fontStyle" in pick:
        return {"family": pick["fontFamily"], "style": pick["fontStyle"]}
    print("no face matching", want, "in", path, [f.get("fontFamily") for f in faces][:12])
    return None

def main():
    global FONT, FONT_REG, FONT_SERIF
    if DOC.exists():
        DOC.unlink()
    run("project", "create", "--project", DOC)
    noto = "/usr/share/fonts/opentype/noto/"
    FONT = import_font(noto + "NotoSansCJK-Bold.ttc", "CJK TC") or FONT
    FONT_REG = import_font(noto + "NotoSansCJK-Regular.ttc", "CJK TC") or FONT_REG
    FONT_SERIF = import_font(noto + "NotoSerifCJK-Bold.ttc", "CJK TC")
    print("fonts:", FONT, FONT_REG, FONT_SERIF)

    for p in PHOTOS:
        run("project", "import-asset", "--project", DOC, "--file", ASSETS / "photos" / f"{p}.jpg", "--asset-id", p, "--kind", "image")
    run("project", "import-asset", "--project", DOC, "--file", ASSETS / "logo_gold.png", "--asset-id", "logo", "--kind", "image")

    ed = WORK / "editable.json"
    run("project", "checkout", "--project", DOC, "--output", ed)
    doc = json.load(open(ed, encoding="utf-8"))
    print("dimensions set at", set_key(doc, "dimensions", {"width": W, "height": H}), "places")
    doc["duration"] = TOTAL
    comp, cpath = find_layers(doc) or (None, None)
    if comp is not None and "duration" in comp:
        comp["duration"] = TOTAL
    doc["backgroundColor"] = [0, 0, 0, 1]
    json.dump(doc, open(ed, "w", encoding="utf-8"), ensure_ascii=False)
    run("project", "commit", "--project", DOC, "--file", ed)

    only = [x for x in os.environ.get("ONLY", "").split(",") if x]
    built, rejected = [], []
    for fn in (scene_S1, scene_S2, scene_S3, scene_S4, scene_S5, scene_S6):
        sid = fn.__name__.split("_")[1]
        if only and sid not in only:
            continue
        sc = fn()
        r = run("project", "apply", "--project", DOC, "--actions", sc.dump(), check=False)
        if r.returncode != 0:
            print(f"!! {sid} REJECTED - continuing with the other scenes", flush=True)
            rejected.append(sid)
            continue
        built.append(sc)
    ov = WORK / "batches" / "overlays.json"
    json.dump(OVERLAYS, open(ov, "w", encoding="utf-8"), ensure_ascii=False)
    r = run("project", "apply", "--project", DOC, "--actions", ov, check=False)
    if r.returncode != 0:
        print("!! overlays REJECTED", flush=True)
        rejected.append("overlays")

    r = run("project", "inspect", "--project", DOC, "--pretty", check=False)
    (WORK / "project.json").write_text(r.stdout, encoding="utf-8")
    print("document size:", DOC.stat().st_size // 1024, "KB")

    for sc in built:
        n = 6
        ts = ",".join(str(sc.t0 + int(sc.dur * k / (n - 1)) - (40 if k == n - 1 else 0)) for k in range(n))
        run("filmstrip", "--project", DOC, "--timestamps-ms", ts, "--frame-rate", FPS, "--items-per-row", 3,
            "--tile-width", 640, "--tile-height", 360, "--samples", 4, "--output", PREV / f"{sc.sid}.png", check=False)
    r = run("evaluate", "--project", DOC, "--checks", "scene3d.framing,fx.text-fit,fx.text-overlap", "--start-ms", 0,
            "--duration-ms", int(round(TOTAL * 1000)), "--fps", 1, check=False)
    (WORK / "checks.jsonl").write_text(r.stdout, encoding="utf-8")
    print("build done:", DOC, "| rejected:", rejected or "none")
    if rejected:
        sys.exit("rejected: " + ",".join(rejected))

if __name__ == "__main__":
    main()
