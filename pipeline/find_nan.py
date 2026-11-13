"""Find which scene ingredient makes the renderer report 'Invalid radiance'.

Builds a series of tiny documents, each adding one ingredient of scene S1, and
previews each with the raster renderer. Prints PASS/FAIL per variant.
Env: TS (tsrct path), FONT_BOLD.
"""
import json, os, subprocess, sys, pathlib, shutil, importlib.util

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.argv = [sys.argv[0]]
spec = importlib.util.spec_from_file_location("build", ROOT / "pipeline" / "build.py")
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)

OUT = ROOT / "project" / ".tesseract-work" / "bisect"
OUT.mkdir(parents=True, exist_ok=True)
TS = B.TS

def tsrct(*args):
    r = subprocess.run([TS] + [str(a) for a in args], capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr)

def variant(name, build_fn, time_s=1.0, overlays=False, font=True, mode="preview"):
    doc = OUT / f"{name}.tsrct"
    if doc.exists():
        doc.unlink()
    tsrct("project", "create", "--project", doc)
    if font:
        rc, out = tsrct("project", "import-font", "--project", doc, "--file", os.environ.get("FONT_BOLD", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"))
    ed = OUT / f"{name}.editable.json"
    tsrct("project", "checkout", "--project", doc, "--output", ed)
    d = json.load(open(ed, encoding="utf-8"))
    B.set_key(d, "dimensions", {"width": 1920, "height": 1080}, [0])
    d["duration"] = 6.0
    comp, _ = B.find_layers(d)
    if comp is not None and "duration" in comp:
        comp["duration"] = 6.0
    json.dump(d, open(ed, "w", encoding="utf-8"))
    rc, out = tsrct("project", "commit", "--project", doc, "--file", ed)
    if rc:
        print(f"{name}: COMMIT FAILED {out[-300:]}"); return
    B.SCENES["S1"] = {"id": "S1", "start": 0.0, "end": 6.0, "dur": 6.0}
    s = B.Scene("S1", 10, 1000)
    build_fn(s)
    p = OUT / f"{name}.json"
    json.dump(s.acts, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    rc, out = tsrct("project", "apply", "--project", doc, "--actions", p)
    if rc:
        print(f"{name}: APPLY FAILED {out[-400:]}"); return
    if overlays:
        B.OVERLAYS.clear()
        B.text2d("2025.01.27 测试", 120, 950, 0.5, 5.5, size=44, color="#9aa3b2", bold=True, tracking=120)
        q = OUT / f"{name}.ov.json"
        json.dump(B.OVERLAYS, open(q, "w", encoding="utf-8"), ensure_ascii=False)
        rc, out = tsrct("project", "apply", "--project", doc, "--actions", q)
        if rc:
            print(f"{name}: OVERLAY APPLY FAILED {out[-400:]}"); return
    if mode == "filmstrip":
        rc, out = tsrct("filmstrip", "--project", doc, "--timestamps-ms", "0,1000,3000", "--frame-rate", 30, "--items-per-row", 3,
                        "--tile-width", 640, "--tile-height", 360, "--samples", 4, "--output", OUT / f"{name}.png")
    else:
        rc, out = tsrct("preview", "--project", doc, "--time", time_s, "--samples", 1, "--output", OUT / f"{name}.png")
    tag = "PASS" if rc == 0 else "FAIL"
    print(f"{name}: {tag} {'' if rc == 0 else out.strip().splitlines()[-1][:160]}", flush=True)

LIN = B.LIN
def cam_angle(s):
    cid = s.id()
    s.acts.append({"type": "addFxScene3DLayer", "compositionId": "main", "layerId": s.layer,
        "item": {"type": "Camera3D", "id": cid, "parentId": None, "name": "Cam", "isHidden": False, "exposure": 0,
                 "transform": {"position": [0, -700, -7600], "rotation": B.euler(None), **B.aim_at((0, -40, 0), s.id(), s.id())},
                 "lens": {"type": "angle", "projection": {"type": "perspective", "angleOfView": 40}}}})
    s.acts.append({"type": "setFxScene3DActiveCamera", "compositionId": "main", "layerId": s.layer, "cameraItemId": cid})
    return cid

def v01(s):  # box + parallel light + angle camera (= smoke, landscape)
    s.mesh({"type": "box", "size": [600, 600, 600]}, (0, 0, 0), dict(base="#2060c0", rough=0.4))
    s.light("parallel", rot=(-45, 0, 0), power=3, shadows=False)
    cam_angle(s)
def v02(s):  # + world
    v01(s); s.world("#000000", 0.015, (0.7, 0.8, 1))
def v03(s):  # physical camera instead of angle
    s.mesh({"type": "box", "size": [600, 600, 600]}, (0, 0, 0), dict(base="#2060c0", rough=0.4))
    s.light("parallel", rot=(-45, 0, 0), power=3, shadows=False)
    s.camera((0, -700, -7600), (0, -40, 0), focal=50, fnum=5.6)
def v04(s):  # area light
    s.mesh({"type": "box", "size": [600, 600, 600]}, (0, 0, 0), dict(base="#2060c0", rough=0.4))
    s.light("area", pos=(-2600, -1900, -1400), aim=(0, 0, 0), power=90000, color=(0.75, 0.85, 1), areaSize=[900, 600])
    cam_angle(s)
def v05(s):  # spot light
    s.mesh({"type": "box", "size": [600, 600, 600]}, (0, 0, 0), dict(base="#2060c0", rough=0.4))
    s.light("spot", pos=(2400, -1500, 2200), aim=(0, 0, 0), power=60000, color=(1, 0.95, 0.9), coneAngle=40, coneFeather=0.4)
    cam_angle(s)
def v06(s):  # point light
    s.mesh({"type": "box", "size": [600, 600, 600]}, (0, 0, 0), dict(base="#2060c0", rough=0.4))
    s.light("point", pos=(0, -900, -900), power=70000, color=(1, 0.62, 0.35), sourceRadius=60)
    cam_angle(s)
def v07(s):  # huge floor
    v01(s); s.mesh({"type": "box", "size": [30000, 40, 30000]}, (0, 320, 0), dict(base="#101114", rough=0.08), name="Floor")
def v08(s):  # metallic material
    s.mesh({"type": "box", "size": [600, 600, 600]}, (0, 0, 0), dict(base="#c8ccd4", rough=0.28, metal=1.0))
    s.light("parallel", rot=(-45, 0, 0), power=3, shadows=False); cam_angle(s)
def v09(s):  # emissive material with strength 0
    s.mesh({"type": "box", "size": [600, 600, 600]}, (0, 0, 0), dict(base="#202020", rough=0.5, emissive="#ff2a1a", estrength=0.0))
    s.light("parallel", rot=(-45, 0, 0), power=3, shadows=False); cam_angle(s)
def v10(s):  # text3d
    s.text3d("-589,000", (0, 190, 0), size=300, depth=90, mat=dict(base="#c8ccd4", rough=0.28, metal=1.0),
             side_mat=dict(base="#6b7078", rough=0.35, metal=1.0), bevel=5)
    s.light("parallel", rot=(-45, 0, 0), power=3, shadows=False); cam_angle(s)
def v11(s):  # text3d without bevel
    s.text3d("-589,000", (0, 190, 0), size=300, depth=90, mat=dict(base="#c8ccd4", rough=0.28, metal=0.0), bevel=0)
    s.light("parallel", rot=(-45, 0, 0), power=3, shadows=False); cam_angle(s)
def v12(s):  # exposure fade animator on the view
    v01(s); s.fade(1200, 1200)
def v13(s):  # camera position animator
    v01(s); s.anim(s.cam if hasattr(s, "cam") else 1004, "position", [(0, (0, -700, -7600), LIN), (6000, (120, -260, -4200), LIN)], "vector3")
def v14(s):  # shadows on
    s.mesh({"type": "box", "size": [600, 600, 600]}, (0, 0, 0), dict(base="#2060c0", rough=0.4))
    s.light("parallel", rot=(-45, 0, 0), power=3, shadows=True); cam_angle(s)
def v15(s):  # full S1
    B.scene_S1.__globals__["Scene"] = lambda sid, layer, base: s  # reuse this scene object
    src = B.scene_S1()
def v16(s):  # grid array
    g, _ = s.group((0, 0, 0), array={"type": "grid", "counts": [5, 1, 5], "spacing": [300, 0, 300]})
    s.mesh({"type": "box", "size": [100, 300, 100]}, (-600, 0, -600), dict(base="#1a1d24", rough=0.7), parent=g)
    s.light("parallel", rot=(-45, 0, 0), power=3, shadows=False); cam_angle(s)
def v17(s):  # bevel modifier
    s.mesh({"type": "box", "size": [600, 600, 600]}, (0, 0, 0), dict(base="#2060c0", rough=0.4),
           modifiers=[{"type": "bevel", "width": 20, "segments": 2, "profile": 0.5, "limitAngle": 30}])
    s.light("parallel", rot=(-45, 0, 0), power=3, shadows=False); cam_angle(s)

variants = [("v01_smoke", v01), ("v02_world", v02), ("v03_physcam", v03), ("v04_area", v04), ("v05_spot", v05),
            ("v06_point", v06), ("v07_floor", v07), ("v08_metal", v08), ("v09_emissive0", v09), ("v10_text3d", v10),
            ("v11_text3d_nobevel", v11), ("v12_fade", v12), ("v14_shadows", v14), ("v16_grid", v16), ("v17_bevelmod", v17)]
only = os.environ.get("ONLY")
for name, fn in (variants if os.environ.get("MODE") != "scenes" else []):
    if only and only not in name:
        continue
    try:
        variant(name, fn)
    except Exception as e:
        print(f"{name}: EXC {e}")
if os.environ.get("MODE") != "scenes":
    variant("v18_overlay2d", v01, overlays=True)
    variant("v19_nofont_smoke", v01, font=False)
    variant("v20_smoke_filmstrip", v01, mode="filmstrip")
    variant("v21_fade_t0", v12, time_s=0.0)
    variant("v22_fade_filmstrip", v12, mode="filmstrip")
    variant("v23_smoke_t0", v01, time_s=0.0)


# ----------------------------------------------------------------- scene-level mode
def scene_doc(name, fns, overlays=False, audio=False):
    """Build a 1920x1080 document of full length holding only the given scene builders."""
    doc = OUT / f"{name}.tsrct"
    if doc.exists():
        doc.unlink()
    tsrct("project", "create", "--project", doc)
    for p in (os.environ.get("FONT_BOLD", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
              os.environ.get("FONT_REG", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")):
        tsrct("project", "import-font", "--project", doc, "--file", p)
    ed = OUT / f"{name}.editable.json"
    tsrct("project", "checkout", "--project", doc, "--output", ed)
    d = json.load(open(ed, encoding="utf-8"))
    B.set_key(d, "dimensions", {"width": 1920, "height": 1080}, [0])
    d["duration"] = B.TOTAL
    comp, _ = B.find_layers(d)
    if comp is not None and "duration" in comp:
        comp["duration"] = B.TOTAL
    d["backgroundColor"] = [0, 0, 0, 1]
    json.dump(d, open(ed, "w", encoding="utf-8"))
    rc, out = tsrct("project", "commit", "--project", doc, "--file", ed)
    if rc:
        print(f"{name}: COMMIT FAILED {out[-300:]}"); return None
    B.OVERLAYS.clear()
    built = []
    for fn in fns:
        s = fn()
        p = OUT / f"{name}.{s.sid}.json"
        json.dump(s.acts, open(p, "w", encoding="utf-8"), ensure_ascii=False)
        rc, out = tsrct("project", "apply", "--project", doc, "--actions", p)
        if rc:
            print(f"{name}: APPLY {s.sid} FAILED {out[-400:]}"); return None
        built.append(s)
    if overlays:
        q = OUT / f"{name}.ov.json"
        json.dump(B.OVERLAYS, open(q, "w", encoding="utf-8"), ensure_ascii=False)
        rc, out = tsrct("project", "apply", "--project", doc, "--actions", q)
        if rc:
            print(f"{name}: OVERLAY APPLY FAILED {out[-400:]}"); return None
    return doc, built

def render_checks(name, doc, t0_ms, dur_ms):
    checks = [("preview_mid", ["preview", "--project", doc, "--time", (t0_ms + min(2000, dur_ms // 2)) / 1000, "--samples", 1, "--output", OUT / f"{name}.mid.png"]),
              ("preview_t0", ["preview", "--project", doc, "--time", t0_ms / 1000, "--samples", 1, "--output", OUT / f"{name}.t0.png"]),
              ("filmstrip", ["filmstrip", "--project", doc, "--timestamps-ms", f"{t0_ms},{t0_ms + 1500},{t0_ms + min(4000, dur_ms - 100)}", "--frame-rate", 30,
                             "--items-per-row", 3, "--tile-width", 640, "--tile-height", 360, "--samples", 4, "--output", OUT / f"{name}.strip.png"])]
    for label, args in checks:
        rc, out = tsrct(*args)
        last = "" if rc == 0 else out.strip().splitlines()[-1][:140]
        print(f"{name} {label}: {'PASS' if rc == 0 else 'FAIL'} {last}", flush=True)

if os.environ.get("MODE") == "scenes":
    fns = [B.scene_S1, B.scene_S2, B.scene_S3, B.scene_S4, B.scene_S5, B.scene_S6, B.scene_S7, B.scene_S8]
    only = os.environ.get("ONLY", "")
    for fn in fns:
        sid = fn.__name__[-2:]
        if only and only not in sid:
            continue
        r = scene_doc(f"solo_{sid}", [fn])
        if r:
            doc, built = r
            render_checks(f"solo_{sid}", doc, built[0].t0, built[0].dur)
    if not only:
        r = scene_doc("all_scenes_noov", fns)
        if r:
            doc, built = r
            render_checks("all_scenes_noov", doc, built[3].t0, built[3].dur)
        r = scene_doc("all_scenes_ov", fns, overlays=True)
        if r:
            doc, built = r
            render_checks("all_scenes_ov", doc, built[3].t0, built[3].dur)
    sys.exit(0)
