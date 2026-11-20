"""XO Tours "about us" ad: narration + timeline.

Placeholder voice: edge-tts (script.json "voice", default zh-TW-HsiaoChenNeural).
A real recording wins: drop <line id>.wav or .mp3 into xotours/project/narration/.

Writes
  project/narration/<id>.mp3       one clip per line
  project/narration/narration.wav  the whole voice track with the gaps baked in
  script_timed.json                lines with start/dur, scene windows (seconds)
"""
import asyncio, json, os, subprocess, pathlib

HERE = pathlib.Path(__file__).resolve().parent
NARR = HERE / "project" / "narration"
NARR.mkdir(parents=True, exist_ok=True)
cfg = json.load(open(HERE / "script.json", encoding="utf-8"))
VOICE = os.environ.get("TTS_VOICE", cfg.get("voice", "zh-TW-HsiaoChenNeural"))
RATE = os.environ.get("TTS_RATE", cfg.get("rate", "+0%"))
LINE_GAP = 0.45
lead = lambda s: cfg["scene_lead"].get(s, cfg["scene_lead"]["default"])
tail = lambda s: cfg["scene_tail"].get(s, cfg["scene_tail"]["default"])
lines = cfg["lines"]

def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout.strip()
    return float(out)

async def synth(line):
    for ext in ("wav", "mp3"):
        own = NARR / f"{line['id']}.{ext}"
        if own.exists() and os.environ.get("TTS_FORCE") != "1":
            line["file"], line["dur"] = own.name, round(probe(own), 3)
            print(line["id"], "kept", line["dur"])
            return
    import edge_tts
    out = NARR / f"{line['id']}.mp3"
    await edge_tts.Communicate(line["zh"], VOICE, rate=RATE).save(str(out))
    line["file"], line["dur"] = out.name, round(probe(out), 3)
    print(line["id"], "tts", line["dur"])

async def main():
    for l in lines:
        await synth(l)
    t, scenes, cur = 0.0, [], None
    for l in lines:
        if cur is None or cur["id"] != l["scene"]:
            if cur is not None:
                cur["end"] = max(t - LINE_GAP + tail(cur["id"]), cur["start"] + cfg["min_scene"].get(cur["id"], 0))
                t = cur["end"]
            cur = {"id": l["scene"], "start": t, "lines": []}
            scenes.append(cur)
            t += lead(l["scene"])
        l["start"] = round(t, 3)
        cur["lines"].append(l["id"])
        t += l["dur"] + LINE_GAP
    cur["end"] = max(t - LINE_GAP + tail(cur["id"]), cur["start"] + cfg["min_scene"].get(cur["id"], 0))
    total = cur["end"]
    for s in scenes:
        s["start"], s["end"] = round(s["start"], 3), round(s["end"], 3)
        s["dur"] = round(s["end"] - s["start"], 3)

    cmd, filt, parts = ["ffmpeg", "-y", "-v", "error"], [], []
    for i, l in enumerate(lines):
        cmd += ["-i", str(NARR / l["file"])]
        ms = int(l["start"] * 1000)
        filt.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=mono,adelay={ms}|{ms}[a{i}]")
        parts.append(f"[a{i}]")
    filt.append("".join(parts) + f"amix=inputs={len(lines)}:normalize=0:dropout_transition=0,apad=whole_dur={total:.3f}[out]")
    cmd += ["-filter_complex", ";".join(filt), "-map", "[out]", "-ar", "48000", "-ac", "1",
            "-t", f"{total:.3f}", str(NARR / "narration.wav")]
    subprocess.run(cmd, check=True)
    json.dump({"title": cfg["title"], "voice": VOICE, "total": round(total, 3), "scenes": scenes, "lines": lines},
              open(HERE / "script_timed.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("TOTAL", round(total, 2), "s")
    for s in scenes:
        print(f"  {s['id']}  {s['start']:6.2f} -> {s['end']:6.2f}  ({s['dur']:.1f}s)")

asyncio.run(main())
