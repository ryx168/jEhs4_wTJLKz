"""Step 4 of the tweet: narration.

Placeholder voice: edge-tts zh-CN-XiaoxiaoNeural, the same voice the AI 日报 channel
uses. Replace with a real recording by dropping WAV/MP3 files named <line id>.wav
into project/narration/ ; this script keeps any file that already exists.

Writes:
  project/narration/<id>.mp3     one clip per line
  project/narration/narration.wav full narration with the scene gaps baked in
  script/script_timed.json       every line with dur / start (seconds) and the
                                 per-scene windows build.py reads
"""
import asyncio, json, os, subprocess, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
NARR = ROOT / "project" / "narration"
NARR.mkdir(parents=True, exist_ok=True)
VOICE = os.environ.get("TTS_VOICE", "zh-CN-XiaoxiaoNeural")
RATE = os.environ.get("TTS_RATE", "+0%")

LINE_GAP = 0.55      # pause between sentences inside a scene
SCENE_LEAD = 1.2     # silence after a scene starts before the first line
SCENE_TAIL = 1.4     # silence after the last line before the next scene
TITLE_SCENE = {"S2": 7.0}   # scenes with no narration: fixed length in seconds
MIN_SCENE = {"S1": 20.0, "S3": 26.0, "S4": 30.0, "S5": 26.0, "S6": 26.0, "S7": 30.0, "S8": 22.0}

lines = json.load(open(ROOT / "script" / "script.json", encoding="utf-8"))

def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout.strip()
    return float(out)

async def synth(line):
    if not line["zh"].strip():
        line["dur"] = 0.0
        line["file"] = None
        return
    for ext in ("wav", "mp3"):
        own = NARR / f"{line['id']}.{ext}"
        if own.exists() and os.environ.get("TTS_FORCE") != "1":
            line["file"] = own.name
            line["dur"] = round(probe(own), 3)
            print(line["id"], "kept", line["dur"])
            return
    import edge_tts
    out = NARR / f"{line['id']}.mp3"
    await edge_tts.Communicate(line["zh"], VOICE, rate=RATE).save(str(out))
    line["file"] = out.name
    line["dur"] = round(probe(out), 3)
    print(line["id"], "tts", line["dur"])

async def main():
    for l in lines:
        await synth(l)

    # Lay the lines out on the timeline, scene by scene.
    t = 0.0
    scenes = []
    cur = None
    for l in lines:
        if cur is None or cur["id"] != l["scene"]:
            if cur is not None and cur["id"] not in TITLE_SCENE:
                cur["end"] = max(t + SCENE_TAIL, cur["start"] + MIN_SCENE.get(cur["id"], 0))
                t = cur["end"]
            cur = {"id": l["scene"], "start": t, "lines": []}
            scenes.append(cur)
            if l["scene"] in TITLE_SCENE:
                cur["end"] = t + TITLE_SCENE[l["scene"]]
                t = cur["end"]
                continue
            t += SCENE_LEAD
        if l["dur"] == 0:
            continue
        l["start"] = round(t, 3)
        cur["lines"].append(l["id"])
        t += l["dur"] + LINE_GAP
    cur["end"] = max(t + SCENE_TAIL, cur["start"] + MIN_SCENE.get(cur["id"], 0))
    total = cur["end"]
    for s in scenes:
        s["start"] = round(s["start"], 3); s["end"] = round(s["end"], 3)
        s["dur"] = round(s["end"] - s["start"], 3)

    # Concatenate into one WAV with silences, so the document needs one audio layer.
    parts = []
    filt = []
    idx = 0
    cmd = ["ffmpeg", "-y", "-v", "error"]
    for l in lines:
        if not l.get("file"):
            continue
        cmd += ["-i", str(NARR / l["file"])]
        filt.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=mono,adelay={int(l['start']*1000)}|{int(l['start']*1000)}[a{idx}]")
        parts.append(f"[a{idx}]")
        idx += 1
    filt.append("".join(parts) + f"amix=inputs={idx}:normalize=0:dropout_transition=0,apad=whole_dur={total:.3f}[out]")
    cmd += ["-filter_complex", ";".join(filt), "-map", "[out]", "-ar", "48000", "-ac", "1",
            "-t", f"{total:.3f}", str(NARR / "narration.wav")]
    subprocess.run(cmd, check=True)

    json.dump({"voice": VOICE, "total": round(total, 3), "scenes": scenes, "lines": lines},
              open(ROOT / "script" / "script_timed.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("TOTAL", round(total, 1), "s;", "narration.wav", round(probe(NARR / "narration.wav"), 2))
    for s in scenes:
        print(f"  {s['id']}  {s['start']:7.2f} -> {s['end']:7.2f}  ({s['dur']:.1f}s)")

asyncio.run(main())
