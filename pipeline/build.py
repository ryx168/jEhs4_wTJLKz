"""Step 3 of the tweet: build every scene as a Tesseract 3D scene.

Reads script/script_timed.json (from tts.py) and writes project/project.tsrct:
  - 1920x1080, document duration = narration length
  - one Scene3D layer per scene (S1..S8), active only in its window
  - 2D title / label layers on top, timed to the narration lines
  - the narration as one Audio layer (optional: the stitch step muxes it anyway)

Every tsrct call is logged; a rejected batch stops the build with the CLI's error.
Scene coordinates: X right, Y DOWN, Z into the screen. Origin = scene centre.
pixelsPerMeter = 100, so 1 m = 100 px. Lights are physical (watts, W/m2).
Material colours are scene-linear; world/2D colours are extended sRGB.

Env: TS (tsrct path, required), FONT_BOLD / FONT_REG (CJK TTC files).
"""
import json, os, subprocess, sys, pathlib, math, random, shutil

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROJ = ROOT / "project"
WORK = PROJ / ".tesseract-work"
PREV = PROJ / "Previews"
for d in (WORK, PREV, WORK / "batches"):
    d.mkdir(parents=True, exist_ok=True)
TS = os.environ.get("TS") or shutil.which("tsrct") or ""
if not TS:
    sys.exit("set TS to the tsrct executable")
DOC = PROJ / "project.tsrct"
W, H = 1920, 1080
FPS = 30
PPM = 100

timed = json.load(open(ROOT / "script" / "script_timed.json", encoding="utf-8"))
SCENES = {s["id"]: s for s in timed["scenes"]}
LINES = {l["id"]: l for l in timed["lines"]}
TOTAL = timed["total"]
FONT = {"family": "Noto Sans CJK SC", "style": "Bold"}
FONT_REG = {"family": "Noto Sans CJK SC", "style": "Regular"}

# ----------------------------------------------------------------- helpers
def run(*args, check=True):
    cmd = [TS] + [str(a) for a in args]
    print("$", " ".join(cmd[1:]), flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = r.stdout.strip()
    if out and len(out) < 2500:
        print(out)
    elif out:
        print(out[:1200] + " ...")
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
    out = []
    for c in srgb(hexstr):
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return [round(v, 5) for v in out]

EASE = {"type": "cubicBezier", "x1": 0.3, "y1": 0, "x2": 0.2, "y2": 1}
EASE_IN = {"type": "cubicBezier", "x1": 0.6, "y1": 0, "x2": 0.9, "y2": 0.4}
EASE_OUT = {"type": "cubicBezier", "x1": 0.1, "y1": 0.5, "x2": 0.3, "y2": 1}
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

class Scene:
    """Collects the action batch for one Scene3D layer."""
    def __init__(self, sid, layer_id, id_base):
        self.sid = sid
        self.layer = layer_id
        self.nid = id_base
        self.acts = []
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
        """scene-local ms of a narration line (+offset s)"""
        return int(round((LINES[line_id]["start"] - SCENES[self.sid]["start"] + plus) * 1000))

    def world(self, bg="#020203", ambient=0.03, ambient_color=(1, 1, 1), fog=None):
        w = {"id": self.world_id, "background": {"type": "color", "color": srgb(bg, 1)},
             "light": {"source": {"type": "color", "color": list(ambient_color) + [1]},
                       "intensity": ambient, "integration": "sampled"}}
        if fog:
            w["fog"] = {"color": fog[0], "startDistance": fog[1], "endDistance": fog[2]}
        self.acts.append({"type": "setFxScene3DWorld", "compositionId": "main", "layerId": self.layer, "world": w})

    def camera(self, pos, aim, focal=50, fnum=8, exposure=0):
        cid = self.id()
        tr = {"position": list(pos), "rotation": euler(None)}
        tr.update(aim_at(aim, self.id(), self.id()))
        self.acts.append({"type": "addFxScene3DLayer", "compositionId": "main", "layerId": self.layer,
            "item": {"type": "Camera3D", "id": cid, "parentId": None, "name": "Camera", "isHidden": False,
                     "transform": tr,
                     "lens": {"type": "physical", "focalLengthMm": focal, "sensorMm": [36, 24], "fNumber": fnum},
                     "exposure": exposure}})
        self.acts.append({"type": "setFxScene3DActiveCamera", "compositionId": "main", "layerId": self.layer, "cameraItemId": cid})
        self.cam = cid
        return cid

    def light(self, kind, pos=None, aim=None, power=1000, color=(1, 1, 1), rot=None, shadows=True, **extra):
        lid = self.id()
        tr = {"position": list(pos) if pos else [0, 0, 0], "rotation": euler(rot)}
        if aim is not None:
            tr.update(aim_at(aim, self.id(), self.id()))
        if kind == "parallel":
            em = {"type": "parallel", "irradiance": power, "angularDiameter": extra.pop("angularDiameter", 0.5)}
        elif kind == "area":
            em = {"type": "area", "power": power,
                  "shape": {"type": "rectangle", "areaSize": extra.pop("areaSize", [500, 500])}}
        else:
            em = {"type": kind, "power": power}
        em.update(extra)
        item = {"type": "Light3D", "id": lid, "parentId": None, "name": f"{kind} light", "isHidden": False,
                "transform": tr, "emitter": em, "color": list(color) + [1], "castsShadows": shadows}
        self.acts.append({"type": "addFxScene3DLayer", "compositionId": "main", "layerId": self.layer, "item": item})
        return lid

    @staticmethod
    def material(slot_id, bind_id, base="#808080", rough=0.5, metal=0.0, emissive=None, estrength=1.0, unlit=False):
        inputs = {"baseColor": {"type": "constant", "value": lin(base)},
                  "roughness": {"type": "constant", "value": rough},
                  "metallic": {"type": "constant", "value": metal}}
        if emissive:
            inputs["emissiveColor"] = {"type": "constant", "value": lin(emissive)}
            inputs["emissiveStrength"] = {"type": "constant", "value": estrength}
        b = {"id": bind_id, "inputs": inputs, "alphaMode": "opaque", "doubleSided": False, "unlit": unlit,
             "transmissionMedium": {"type": "sheet"}}
        return {"id": slot_id, "name": "Finish", "binding": b}

    def mesh(self, geometry, pos, mat, rot=None, scale=None, parent=None, name="Mesh", modifiers=None, shadows=True):
        did, iid, sid, bid = self.id(), self.id(), self.id(), self.id()
        item = {"type": "Mesh3D", "id": iid, "parentId": parent, "name": name, "dataId": did, "packing": "whole",
                "isHidden": False, "transform": tf3(pos, rot, scale), "materialSlots": [self.material(sid, bid, **mat)],
                "regionSlots": [{"region": "primary", "slotId": sid}, {"region": "side", "slotId": sid}],
                "castsShadows": shadows, "receivesShadows": True}
        if modifiers:
            item["modifiers"] = [dict(m, id=self.id()) for m in modifiers]
        self.acts.append({"type": "addFxScene3DFragment", "compositionId": "main", "layerId": self.layer,
            "data": [{"type": "mesh", "id": did, "name": name + " geometry", "geometry": geometry,
                      "regions": [{"key": "primary", "name": "Primary"}, {"key": "side", "name": "Side"}]}],
            "items": [item]})
        return iid, bid

    def text3d(self, text, pos, size=200, depth=40, mat=None, side_mat=None, bevel=0, rot=None, name="Text", parent=None):
        did, iid = self.id(), self.id()
        mat = mat or {}
        s1, b1, s2, b2 = self.id(), self.id(), self.id(), self.id()
        data = {"type": "text", "id": did, "name": name + " geometry", "text": text, "fontFamily": FONT["family"],
                "fontStyle": FONT["style"], "fontSize": size, "depth": depth, "justification": "center", "tracking": 0,
                "regions": [{"key": "front", "name": "Front"}, {"key": "back", "name": "Back"}, {"key": "side", "name": "Side"}]}
        if bevel:
            data["bevelSize"] = bevel
            data["bevelSegments"] = 3
        item = {"type": "Text3D", "id": iid, "parentId": parent, "name": name, "dataId": did, "isHidden": False,
                "transform": tf3(pos, rot),
                "materialSlots": [self.material(s1, b1, **mat), self.material(s2, b2, **(side_mat or mat))],
                "regionSlots": [{"region": "front", "slotId": s1}, {"region": "back", "slotId": s1}, {"region": "side", "slotId": s2}],
                "castsShadows": True, "receivesShadows": True}
        self.acts.append({"type": "addFxScene3DFragment", "compositionId": "main", "layerId": self.layer,
                          "data": [data], "items": [item]})
        return iid, b1, did

    def group(self, pos=(0, 0, 0), array=None, name="Group", parent=None):
        gid = self.id()
        item = {"type": "Group3D", "id": gid, "parentId": parent, "name": name, "isHidden": False, "transform": tf3(pos)}
        aid = None
        if array:
            aid = self.id()
            item["array"] = dict(array, id=aid)
        self.acts.append({"type": "addFxScene3DFragment", "compositionId": "main", "layerId": self.layer,
                          "data": [], "items": [item]})
        return gid, aid

    def anim(self, item, prop, keys, kind="float"):
        """keys: list of (ms, value, easing)."""
        kf = []
        for n, (t, v, e) in enumerate(keys):
            kf.append({"id": f"{self.sid}-{item}-{prop}-{n}", "layerTime": int(t),
                       "value": {"type": kind, "value": (list(v) if kind != "float" else v)}, "easing": e})
        self.acts.append({"type": "setFxAnimator", "compositionId": "main",
            "target": {"type": "styleProperty", "layerId": self.layer, "itemId": item, "propertyName": prop},
            "animator": {"type": "keyframes", "enabled": True, "keyframes": kf}, "dependencies": [], "layerRefBindings": []})

    def fade(self, t_in=1200, t_out=1200):
        """Exposure fade on the scene view: black -> scene -> black."""
        d = self.dur
        self.anim(self.view_id, "exposure", [(0, -9, LIN), (t_in, 0, EASE_OUT), (d - t_out, 0, LIN), (d - 40, -9, EASE_IN)])

    def dump(self):
        p = WORK / "batches" / f"{self.sid}.json"
        json.dump(self.acts, open(p, "w", encoding="utf-8"), ensure_ascii=False)
        return p

# ----------------------------------------------------------------- 2D overlays
OVERLAYS = []
_layer_ids = iter(range(100, 400))
_key_n = [0]

def text2d(text, x, y, t_start, t_end, size=44, color="#ffffff", align="left", box_w=None, bold=True, fade=400, tracking=0):
    lid = next(_layer_ids)
    f = FONT if bold else FONT_REG
    st = {"text": text, "fontFamily": f["family"], "fontStyle": f["style"], "fontSize": size,
          "fillColor": srgb(color, 1), "justification": align, "strokeWidth": 0, "tracking": tracking}
    if box_w:
        st.update({"boxText": True, "boxPosition": [0, 0], "boxSize": [box_w, int(size * 1.7)]})
    s, e = int(t_start * 1000), int(t_end * 1000)
    d = max(e - s, 200)
    OVERLAYS.append({"type": "createFxTextLayer", "compositionId": "main", "insertIndex": 0, "layerId": lid,
        "name": text[:24], "activeRange": {"start": s, "duration": d},
        "transform": {"anchorPoint": [0, 0], "position": [x, y], "scale": [100, 100], "rotation": 0, "opacity": 100},
        "sourceText": st})
    if fade and d > 3 * fade:
        _key_n[0] += 1
        k = _key_n[0]
        OVERLAYS.append({"type": "setFxPropertyKeyframes", "compositionId": "main",
            "property": {"layerId": lid, "propertyType": "opacity"},
            "keyframes": [
                {"id": f"ov{k}-a", "layerTime": 0, "value": {"type": "float", "value": 0}, "easing": LIN},
                {"id": f"ov{k}-b", "layerTime": fade, "value": {"type": "float", "value": 100}, "easing": EASE_OUT},
                {"id": f"ov{k}-c", "layerTime": d - fade, "value": {"type": "float", "value": 100}, "easing": LIN},
                {"id": f"ov{k}-d", "layerTime": d, "value": {"type": "float", "value": 0}, "easing": EASE_IN}]})
    return lid

def line_window(line_id, lead=0.0, tail=0.6):
    l = LINES[line_id]
    return l["start"] + lead, l["start"] + l["dur"] + tail

# ----------------------------------------------------------------- scenes
def scene_S1():
    s = Scene("S1", 10, 1000)
    s.world("#000000", 0.015, (0.7, 0.8, 1))
    s.mesh({"type": "box", "size": [30000, 40, 30000]}, (0, 220, 0), dict(base="#101114", rough=0.08), name="Floor")
    s.text3d("-589,000,000,000", (0, 190, 0), size=300, depth=90,
             mat=dict(base="#c8ccd4", rough=0.28, metal=1.0), side_mat=dict(base="#6b7078", rough=0.35, metal=1.0),
             bevel=5, name="Number")
    s.light("area", pos=(-2600, -1900, -1400), aim=(0, 0, 0), power=90000, color=(0.75, 0.85, 1), areaSize=[900, 600])
    s.light("spot", pos=(2400, -1500, 2200), aim=(0, 0, 0), power=60000, color=(1, 0.95, 0.9), coneAngle=40, coneFeather=0.4)
    cam = s.camera((0, -700, -7600), (0, -40, 0), focal=50, fnum=5.6)
    s.anim(cam, "position", [(0, (0, -700, -7600), LIN), (s.dur, (120, -260, -4200), LIN)], "vector3")
    s.fade(1500, 1000)
    text2d("2025.01.27", 120, 950, SCENES["S1"]["start"] + 3.0, SCENES["S1"]["end"] - 0.8, size=44, color="#9aa3b2", bold=False, tracking=120)
    return s

def scene_S2():
    s = Scene("S2", 11, 2000)
    s.world("#000000", 0.02, (1, 0.9, 0.8))
    s.mesh({"type": "box", "size": [30000, 40, 30000]}, (0, 240, 0), dict(base="#15120f", rough=0.12), name="Floor")
    s.text3d("DeepSeek 冲击日", (0, 120, 0), size=260, depth=70,
             mat=dict(base="#f2e6d6", rough=0.35, metal=0.2), side_mat=dict(base="#8a5a2b", rough=0.4, metal=0.6),
             bevel=4, name="Title")
    s.light("point", pos=(0, 700, -900), power=70000, color=(1, 0.62, 0.35), sourceRadius=60)
    s.light("area", pos=(1500, -2200, -2000), aim=(0, 0, 0), power=40000, color=(0.7, 0.8, 1), areaSize=[800, 800])
    cam = s.camera((0, -80, -3600), (0, 0, 0), focal=50, fnum=4)
    s.anim(cam, "position", [(0, (0, -80, -3600), LIN), (s.dur, (0, -140, -3250), LIN)], "vector3")
    s.fade(900, 900)
    text2d("一个周末，六千亿美元", 0, 760, SCENES["S2"]["start"] + 1.6, SCENES["S2"]["end"] - 0.8, size=54,
           color="#e8c9a0", align="center", box_w=W, bold=False)
    return s

def scene_S3():
    s = Scene("S3", 12, 3000)
    s.world("#02030a", 0.02, (0.5, 0.65, 1))
    s.mesh({"type": "box", "size": [60000, 40, 60000]}, (0, 20, 0), dict(base="#05070d", rough=0.05), name="Ground")
    # city: three interleaved grids of blocks at three heights
    for k, (h, off, n, sp) in enumerate(((160, (0, 0), 19, 260), (380, (130, 130), 18, 260), (700, (65, 195), 9, 520))):
        g, _ = s.group((off[0], 0, off[1]), array={"type": "grid", "counts": [n, 1, n], "spacing": [sp, 0, sp]}, name=f"City{k}")
        s.mesh({"type": "box", "size": [100 - k * 12, h, 100 - k * 12]}, (-(n - 1) / 2 * sp, -h / 2, -(n - 1) / 2 * sp),
               dict(base="#1a1d24", rough=0.7), parent=g, name=f"Block{k}")
    s.mesh({"type": "box", "size": [220, 1400, 220]}, (0, -700, 0), dict(base="#232833", rough=0.5, metal=0.3), name="Tower")
    for i in range(12):
        s.mesh({"type": "box", "size": [226, 18, 226]}, (0, -120 - i * 110, 0),
               dict(base="#000000", rough=0.6, emissive="#ffb262", estrength=3.5), name=f"Windows{i}", shadows=False)
    s.light("area", pos=(-4000, -5000, -3000), aim=(0, -600, 0), power=600000, color=(0.55, 0.7, 1), areaSize=[2500, 2500])
    s.light("point", pos=(0, -1480, 0), power=30000, color=(1, 0.7, 0.4), sourceRadius=40)
    cam = s.camera((-2500, -13000, -16000), (0, -600, 0), focal=35, fnum=5.6)
    s.anim(cam, "position", [(0, (-2500, -13000, -16000), LIN), (int(s.dur * 0.75), (1400, -1500, -2600), EASE),
                             (s.dur, (1700, -1300, -2300), LIN)], "vector3")
    s.fade(1200, 1000)
    a, b = line_window("s3a", 0.3, 1.0)
    text2d("杭州 · Hangzhou", 120, 900, a, b, size=48)
    a, b = line_window("s3c", 0.5, 2.0)
    text2d("幻方量化  →  DeepSeek   2023", 120, 900, a, b, size=48)
    return s

def scene_S4():
    s = Scene("S4", 13, 4000)
    s.world("#000000", 0.03, (0.6, 0.75, 1))
    s.mesh({"type": "box", "size": [30000, 40, 30000]}, (0, 60, 0), dict(base="#0c0e12", rough=0.15), name="Bench")
    s.mesh({"type": "box", "size": [900, 40, 900]}, (0, 20, 0), dict(base="#0e1a14", rough=0.45), name="Package",
           modifiers=[{"type": "bevel", "width": 6, "segments": 2, "profile": 0.5, "limitAngle": 30}])
    s.mesh({"type": "box", "size": [420, 24, 420]}, (0, -12, 0), dict(base="#b8bcc4", rough=0.18, metal=1.0), name="Die")
    pins, _ = s.group((0, 0, 0), array={"type": "grid", "counts": [14, 1, 14], "spacing": [60, 0, 60]}, name="Pins")
    s.mesh({"type": "box", "size": [22, 10, 22]}, (-6.5 * 60, -29, -6.5 * 60), dict(base="#d4a94a", rough=0.3, metal=1.0),
           parent=pins, name="Pin", shadows=False)
    lanes = []
    for i, x in enumerate((-300, -100, 100, 300)):
        _, b = s.mesh({"type": "box", "size": [8, 6, 860]}, (x, -28, 0), dict(base="#202020", rough=0.5, emissive="#ff2a1a", estrength=0.0),
                      name=f"Lane{i}", shadows=False)
        lanes.append(b)
    t_cut = s.at("s4b", 1.0)
    for b in lanes:
        s.anim(b, "emissiveStrength", [(t_cut, 0, LIN), (t_cut + 400, 7, EASE_OUT), (s.at("s4d", 0.5), 7, LIN), (s.at("s4d", 1.3), 1.2, EASE)])
    s.light("area", pos=(-1800, -1600, -1200), aim=(0, 0, 0), power=70000, color=(0.7, 0.82, 1), areaSize=[700, 700])
    s.light("spot", pos=(1600, -900, 1500), aim=(0, 0, 0), power=35000, color=(1, 0.8, 0.6), coneAngle=45, coneFeather=0.5)
    cam = s.camera((-1300, -800, -1500), (0, -10, 0), focal=50, fnum=4)
    keys, n = [], 7
    for k in range(n):
        ang = math.radians(-130 + k * (150 / (n - 1)))
        r = 2000 - k * 60
        keys.append((int(s.dur * k / (n - 1)), (r * math.sin(ang), -800 + k * 30, -r * math.cos(ang)), LIN))
    s.anim(cam, "position", keys, "vector3")
    s.fade(1000, 900)
    a, b = line_window("s4a", 0.4, 1.5)
    text2d("NVIDIA H800", 120, 900, a, b, size=48)
    a, b = line_window("s4b", 1.0, 1.5)
    text2d("互联带宽  ↓ 50%+", 120, 900, a, b, size=48, color="#ff6a5a")
    return s

def scene_S5():
    s = Scene("S5", 14, 5000)
    s.world("#000000", 0.02, (1, 0.95, 0.85))
    s.mesh({"type": "box", "size": [30000, 40, 30000]}, (0, 20, 0), dict(base="#121010", rough=0.1), name="Floor")
    gold = dict(base="#f3c75a", rough=0.28, metal=1.0)
    coin = {"type": "cylinder", "radius": 150, "height": 16}
    gl, al = s.group((-700, 0, 0), array={"type": "linear", "count": 1, "offset": [0, -18, 0]}, name="Left stack")
    s.mesh(coin, (0, -8, 0), gold, parent=gl, name="Coin")
    gr, ar = s.group((700, 0, 0), array={"type": "linear", "count": 1, "offset": [0, -18, 0]}, name="Right stack")
    s.mesh(coin, (0, -8, 0), gold, parent=gr, name="Coin")
    t0 = s.at("s5a", 2.5)
    s.anim(al, "count", [(t0, 1, LIN), (t0 + 2000, 6, EASE_OUT)])
    t1 = s.at("s5b", 0.8)
    s.anim(ar, "count", [(t1, 1, LIN), (t1 + 4500, 110, EASE_IN)])
    s.text3d("$5.6M", (-700, -220, -220), size=110, depth=30, mat=dict(base="#f0f0f0", rough=0.4), name="L label")
    s.text3d("$100M+", (700, -220, -220), size=110, depth=30, mat=dict(base="#f0f0f0", rough=0.4), name="R label")
    s.light("area", pos=(-2000, -2600, -2400), aim=(0, -600, 0), power=160000, color=(1, 0.93, 0.8), areaSize=[1200, 1200])
    s.light("spot", pos=(2500, -2000, 1800), aim=(700, -800, 0), power=90000, color=(1, 0.85, 0.6), coneAngle=50, coneFeather=0.5)
    cam = s.camera((-1500, -300, -2200), (-700, -150, 0), focal=50, fnum=5.6)
    s.anim(cam, "position", [(0, (-1500, -300, -2200), LIN), (t1, (-900, -500, -2600), EASE),
                             (t1 + 4500, (300, -2200, -5200), EASE), (s.dur, (400, -2300, -5400), LIN)], "vector3")
    s.fade(1000, 900)
    a, b = line_window("s5a", 0.2, 1.0)
    text2d("DeepSeek-V3  ·  2024.12", 120, 900, a, b, size=48)
    a, b = line_window("s5c", 0.3, 1.0)
    text2d("* 不含研发、实验与前期投入", 120, 900, a, b, size=40, color="#c9c9c9", bold=False)
    return s

def scene_S6():
    s = Scene("S6", 15, 6000)
    s.world("#000000", 0.03, (0.6, 0.7, 1))
    s.mesh({"type": "box", "size": [30000, 40, 30000]}, (0, 460, 0), dict(base="#0a0b10", rough=0.07), name="Floor")
    def phone(parent, pos, screen_strength):
        s.mesh({"type": "box", "size": [420, 880, 26]}, pos, dict(base="#1c1d22", rough=0.3, metal=0.8), parent=parent,
               name="Phone", modifiers=[{"type": "bevel", "width": 10, "segments": 3, "profile": 0.5, "limitAngle": 30}])
        _, sb = s.mesh({"type": "box", "size": [392, 850, 4]}, (pos[0], pos[1], pos[2] - 13),
                       dict(base="#000000", rough=0.2, emissive="#1d3b8a", estrength=screen_strength), parent=parent, name="Screen", shadows=False)
        return sb
    phone(None, (0, 0, 0), 2.0)
    tile, _ = s.mesh({"type": "box", "size": [150, 150, 8]}, (0, 330, -18), dict(base="#ffffff", rough=0.4, emissive="#e8f0ff", estrength=2.5),
                     name="App tile", shadows=False, modifiers=[{"type": "bevel", "width": 18, "segments": 3, "profile": 0.5, "limitAngle": 30}])
    tr = s.at("s6b", 0.8)
    s.anim(tile, "position", [(tr, (0, 330, -18), LIN), (tr + 2600, (0, -250, -18), EASE)], "vector3")
    ring, _ = s.group((0, 0, 0), array={"type": "radial", "count": 7, "radius": 1150, "startAngle": 0, "sweep": 360,
                                        "axis": "y", "orient": True, "includeEnd": False}, name="Ring")
    ring_sb = phone(ring, (0, 0, 1150), 0.0)
    t2 = s.at("s6b", 2.0)
    s.anim(ring_sb, "emissiveStrength", [(t2, 0, LIN), (t2 + 1500, 1.8, EASE_OUT)])
    s.light("area", pos=(0, -3000, -1200), aim=(0, 0, 0), power=120000, color=(0.85, 0.9, 1), areaSize=[1500, 1500])
    cam = s.camera((-600, -2300, -2900), (0, 0, 0), focal=35, fnum=4)
    s.anim(cam, "position", [(0, (-600, -2300, -2900), LIN), (s.dur, (500, -1500, -2300), LIN)], "vector3")
    s.fade(1000, 900)
    a, b = line_window("s6a", 0.3, 1.2)
    text2d("DeepSeek-R1  ·  2025.01.20", 120, 900, a, b, size=48)
    a, b = line_window("s6b", 1.0, 1.5)
    text2d("App Store  #1", 120, 900, a, b, size=48)
    return s

def scene_S7():
    s = Scene("S7", 16, 7000)
    s.world("#000000", 0.02, (1, 0.6, 0.5))
    s.mesh({"type": "box", "size": [40000, 40, 40000]}, (0, 20, 0), dict(base="#0b0a0c", rough=0.06), name="Floor")
    rnd = random.Random(27)
    green = dict(base="#2bb673", rough=0.4, emissive="#2bb673", estrength=0.35)
    redm = dict(base="#e0352b", rough=0.4, emissive="#ff3b2e", estrength=0.5)
    for i in range(-16, 17):
        if i == 0:
            continue
        h = rnd.randint(70, 320)
        s.mesh({"type": "box", "size": [48, h, 48]}, (i * 90, -h / 2, 600), green if rnd.random() < 0.55 else redm, name=f"Bar{i}", shadows=False)
    big, _ = s.mesh({"type": "box", "size": [150, 1100, 150]}, (0, -3200, 0), dict(base="#d81e1e", rough=0.35, emissive="#ff2d2d", estrength=2.0), name="NVDA")
    t_open = s.at("s7b", 0.6)
    s.anim(big, "position", [(t_open, (0, -3200, 0), LIN), (t_open + 1100, (0, -550, 0), EASE_IN)], "vector3")
    t3 = s.at("s7c", 0.5)
    for k, (x, h) in enumerate(((-520, 700), (520, 560), (-900, 820))):
        bar, _ = s.mesh({"type": "box", "size": [110, h, 110]}, (x, -3000, 150), dict(base="#b71c1c", rough=0.4, emissive="#ff3b2e", estrength=1.2), name=f"Other{k}")
        s.anim(bar, "position", [(t3 + k * 900, (x, -3000, 150), LIN), (t3 + k * 900 + 900, (x, -h / 2, 150), EASE_IN)], "vector3")
    s.light("area", pos=(-2500, -2800, -2500), aim=(0, -400, 0), power=120000, color=(0.8, 0.85, 1), areaSize=[1500, 1500])
    s.light("point", pos=(0, -1400, -400), power=40000, color=(1, 0.3, 0.25), sourceRadius=80)
    cam = s.camera((-900, -1500, -3600), (0, -350, 100), focal=35, fnum=5.6)
    s.anim(cam, "position", [(0, (-900, -1500, -3600), LIN), (t_open, (-500, -1000, -3000), EASE),
                             (t_open + 1100, (-300, -200, -2200), EASE_IN), (s.dur, (500, -60, -1900), LIN)], "vector3")
    s.fade(900, 1000)
    a, b = line_window("s7b", 0.9, 1.2)
    text2d("NVDA  −17%     −$589B", 120, 900, a, b, size=56, color="#ff5a4e")
    a, b = line_window("s7c", 0.5, 1.2)
    text2d("AVGO −17%    TSM −13%    CEG −21%", 120, 970, a, b, size=44, color="#ff8a7a")
    return s

def scene_S8():
    s = Scene("S8", 17, 8000)
    s.world("#000000", 0.015, (0.6, 0.8, 1))
    s.mesh({"type": "box", "size": [60000, 40, 60000]}, (0, 220, 0), dict(base="#0a0c10", rough=0.06), name="Floor")
    racks, _ = s.group((0, 0, 0), array={"type": "grid", "counts": [16, 1, 24], "spacing": [300, 0, 320]}, name="Racks")
    s.mesh({"type": "box", "size": [220, 440, 140]}, (-7.5 * 300, -20, 900), dict(base="#15171c", rough=0.5, metal=0.4), parent=racks, name="Rack")
    _, ledb = s.mesh({"type": "box", "size": [200, 6, 4]}, (-7.5 * 300, -160, 900 - 72), dict(base="#000000", rough=0.5, emissive="#4cff9a", estrength=0.0),
                     parent=racks, name="LED", shadows=False)
    t_on = s.at("s8b", 0.5)
    s.anim(ledb, "emissiveStrength", [(0, 0, LIN), (t_on, 0.2, LIN), (t_on + 3000, 6, EASE_OUT)])
    num, _, _ = s.text3d("+ 589,000,000,000", (0, 420, -400), size=220, depth=60, mat=dict(base="#3ddc84", rough=0.3, metal=0.7),
                         side_mat=dict(base="#1e7a4a", rough=0.4, metal=0.7), bevel=4, name="Green number")
    s.anim(num, "position", [(0, (0, 420, -400), LIN), (s.at("s8a", 1.5), (0, 420, -400), LIN), (s.at("s8a", 4.5), (0, 190, -400), EASE)], "vector3")
    warm = s.light("area", pos=(-3000, -3500, -2500), aim=(0, -200, 0), power=10000, color=(1, 0.8, 0.6), areaSize=[2500, 2500])
    s.anim(warm, "power", [(0, 10000, LIN), (t_on, 10000, LIN), (t_on + 4000, 320000, EASE)])
    s.light("spot", pos=(2000, -1800, -2200), aim=(0, 0, -400), power=70000, color=(0.8, 0.9, 1), coneAngle=35, coneFeather=0.5)
    cam = s.camera((0, -420, -4200), (0, 0, -400), focal=50, fnum=5.6)
    s.anim(cam, "position", [(0, (0, -420, -4200), LIN), (s.dur, (0, -900, -5600), LIN)], "vector3")
    s.fade(1200, 1800)
    a, _ = line_window("s8c", 1.0, 3.0)
    text2d("下一集 · 从沙子到 H100", 0, 820, a, SCENES["S8"]["end"] - 0.3, size=54, align="center", box_w=W)
    text2d("AI 日报", 0, 900, a, SCENES["S8"]["end"] - 0.3, size=40, color="#bfbfbf", align="center", box_w=W, bold=False)
    return s

# ----------------------------------------------------------------- document
def find_layers(node, path="doc"):
    """Return (container dict, path) of the first dict holding a 'layers' list."""
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
            if k == key and not isinstance(v, (dict, list)):
                node[k] = value; count[0] += 1
            elif k == key and isinstance(v, dict) and set(v) >= {"width", "height"}:
                node[k] = value; count[0] += 1
            else:
                set_key(v, key, value, count)
    elif isinstance(node, list):
        for v in node:
            set_key(v, key, value, count)
    return count[0]

def import_font(path, want="CJK SC"):
    r = run("project", "import-font", "--project", DOC, "--file", path)
    try:
        info = json.loads(r.stdout)
    except Exception:
        return None
    faces = info.get("faces") or [info]
    pick = next((f for f in faces if want in str(f.get("fontFamily", ""))), faces[0])
    if "fontFamily" in pick and "fontStyle" in pick:
        return {"family": pick["fontFamily"], "style": pick["fontStyle"]}
    return None

def main():
    global FONT, FONT_REG
    if DOC.exists():
        DOC.unlink()
    run("project", "create", "--project", DOC)
    (WORK / "document.schema.json").write_text(run("project", "schema", "--document", check=False).stdout, encoding="utf-8")

    FONT = import_font(os.environ.get("FONT_BOLD", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")) or FONT
    FONT_REG = import_font(os.environ.get("FONT_REG", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")) or FONT_REG
    print("fonts:", FONT, FONT_REG)
    run("project", "inspect-fonts", "--project", DOC, "--pretty", check=False)

    # canvas + duration (document-level edit)
    ed = WORK / "editable.json"
    run("project", "checkout", "--project", DOC, "--output", ed)
    doc = json.load(open(ed, encoding="utf-8"))
    print("document keys:", list(doc.keys()))
    n = set_key(doc, "dimensions", {"width": W, "height": H})
    print("dimensions set at", n, "places")
    doc["duration"] = TOTAL
    comp, cpath = find_layers(doc) or (None, None)
    print("composition at", cpath, "layers:", len(comp["layers"]) if comp else None)
    if comp is not None and "duration" in comp:
        comp["duration"] = TOTAL
    doc["backgroundColor"] = [0, 0, 0, 1]
    json.dump(doc, open(ed, "w", encoding="utf-8"), ensure_ascii=False)
    run("project", "commit", "--project", DOC, "--file", ed)

    # scenes
    built = []
    for fn in (scene_S1, scene_S2, scene_S3, scene_S4, scene_S5, scene_S6, scene_S7, scene_S8):
        sc = fn()
        run("project", "apply", "--project", DOC, "--actions", sc.dump())
        built.append(sc)
    ov = WORK / "batches" / "overlays.json"
    json.dump(OVERLAYS, open(ov, "w", encoding="utf-8"), ensure_ascii=False)
    run("project", "apply", "--project", DOC, "--actions", ov)

    # narration as an Audio layer: best effort, the stitch step muxes the WAV anyway
    nar = PROJ / "narration" / "narration.wav"
    if nar.exists():
        r = run("project", "import-asset", "--project", DOC, "--file", nar, "--asset-id", "narration", "--kind", "audio", check=False)
        if r.returncode == 0:
            run("project", "checkout", "--project", DOC, "--output", ed)
            doc = json.load(open(ed, encoding="utf-8"))
            comp, _ = find_layers(doc)
            total_ms = int(round(TOTAL * 1000))
            comp["layers"].append({
                "id": 1, "name": "Narration", "type": "Audio",
                "playback": {"type": "windowed", "inputRange": {"start": 0, "duration": total_ms},
                             "mapping": {"type": "linear", "input": {"start": 0, "duration": total_ms}, "output": {"start": 0, "duration": total_ms}},
                             "inputOffsetMs": 0},
                "sourceRange": {"start": 0, "duration": total_ms}, "sourceIntrinsicDuration": total_ms,
                "source": {"assetId": "narration"}, "volume": 1.0, "captionsEnabled": False})
            json.dump(doc, open(ed, "w", encoding="utf-8"), ensure_ascii=False)
            r = run("project", "commit", "--project", DOC, "--file", ed, check=False)
            print("audio layer:", "ok" if r.returncode == 0 else "REJECTED (narration will be muxed by ffmpeg instead)")

    r = run("project", "inspect", "--project", DOC, "--pretty", check=False)
    (WORK / "project.json").write_text(r.stdout, encoding="utf-8")
    print("document size:", DOC.stat().st_size // 1024, "KB")

    # one raster filmstrip per scene for review
    for sc in built:
        n = 6
        ts = ",".join(str(sc.t0 + int(sc.dur * k / (n - 1)) - (40 if k == n - 1 else 0)) for k in range(n))
        run("filmstrip", "--project", DOC, "--timestamps-ms", ts, "--frame-rate", FPS, "--items-per-row", 3,
            "--tile-width", 640, "--tile-height", 360, "--samples", 4, "--output", PREV / f"{sc.sid}.png", check=False)
    total_ms = int(round(TOTAL * 1000))
    r = run("evaluate", "--project", DOC, "--checks", "scene3d.framing,fx.text-fit,fx.text-overlap", "--start-ms", 0,
            "--duration-ms", total_ms, "--fps", 1, check=False)
    (WORK / "checks.jsonl").write_text(r.stdout, encoding="utf-8")
    print("build done:", DOC)

if __name__ == "__main__":
    main()
