#!/usr/bin/env python3
"""Synthesise a warm, royalty-free music bed for the XO Tours ad: project/bgm.wav.

Nothing sampled. A slow major-key pad (C - G/B - Am - F, then F - G - C for the
close), a soft bell motif on the pentatonic scale, and a low drone. Scene starts
from script_timed.json get a gentle bell accent; the last scene swells.
Usage: python make_bgm.py [--seconds N]  (default: the narration length)
"""
import argparse, json, pathlib, wave
import numpy as np

SR = 48000
HERE = pathlib.Path(__file__).resolve().parent

def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)

def pad(freqs, n, rng):
    t = np.arange(n) / SR
    out = np.zeros(n)
    for f in freqs:
        for det in (-0.35, 0.0, 0.35):
            ff = f * 2 ** (det / 1200)
            ph = rng.uniform(0, 2 * np.pi)
            out += np.sin(2 * np.pi * ff * t + ph) * 0.5 + np.sin(2 * np.pi * ff * 2 * t + ph) * 0.08
    att = np.minimum(1, t / 1.2)
    rel = np.minimum(1, (t[-1] - t) / 1.2 + 1e-9)
    return out * att * rel / (len(freqs) * 3)

def bell(f, dur):
    n = int(SR * dur)
    t = np.arange(n) / SR
    env = np.exp(-t * 3.2) * np.minimum(1, t / 0.004)
    return (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t * 4)) * env

def smooth(x, k=48):
    c = np.cumsum(np.insert(x, 0, 0.0))
    y = (c[k:] - c[:-k]) / k
    return np.concatenate([y, np.full(k - 1, y[-1])])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float)
    ap.add_argument("--seed", type=int, default=1994)
    a = ap.parse_args()
    timed = json.load(open(HERE / "script_timed.json", encoding="utf-8"))
    total = a.seconds or timed["total"]
    rng = np.random.default_rng(a.seed)
    n = int(SR * (total + 0.5))
    mix = np.zeros(n)

    chords = [[48, 55, 64, 67], [47, 55, 62, 67], [45, 52, 60, 64], [41, 53, 57, 60]]   # C  G/B  Am  F
    close = [[41, 53, 57, 60], [43, 55, 59, 62], [36, 48, 55, 64, 67]]                  # F  G  C
    bar = 4.0
    last = timed["scenes"][-1]["start"]
    sched, t, i = [], 0.0, 0
    while t + 0.5 < last:                       # loop the progression up to the last scene
        d = min(bar, last - t)
        sched.append((t, d, chords[i % len(chords)])); t += d; i += 1
    part = (total - last) / len(close)          # F - G - C fills the close
    sched += [(last + k * part, part, ch) for k, ch in enumerate(close)]
    for st, d, ch in sched:
        s0 = int(st * SR)
        seg = pad([hz(m) for m in ch], max(1, min(int((d + 1.2) * SR), n - s0)), rng)   # 1.2 s overlap
        mix[s0:s0 + len(seg)] += seg
    mix = smooth(mix, 24)

    drone_t = np.arange(n) / SR
    mix += 0.06 * np.sin(2 * np.pi * hz(36) * drone_t) * np.minimum(1, drone_t / 3)

    penta = [72, 74, 76, 79, 81, 84]
    for s in timed["scenes"]:
        for k in range(3):
            st = s["start"] + 0.15 + k * 0.42
            f = hz(penta[(k * 2 + int(s["start"])) % len(penta)])
            b = bell(f, 2.5) * (0.16 - 0.04 * k)
            i0 = int(st * SR)
            mix[i0:i0 + len(b)] += b[: max(0, n - i0)]

    tt = np.arange(n) / SR
    swell = 1 + 0.6 * np.clip((tt - last) / 4, 0, 1)
    env = np.minimum(1, tt / 1.5) * np.clip((total + 0.3 - tt) / 3.0, 0, 1) * swell
    mix *= env
    mix /= np.max(np.abs(mix)) + 1e-9
    mix *= 0.7
    out = HERE / "project" / "bgm.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    pcm = (mix * 32767).astype("<i2")
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
    print("bgm", out, round(n / SR, 2), "s")

if __name__ == "__main__":
    main()
