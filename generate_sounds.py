"""Generate the free sound-effects library for the editor.

Every sound here is SYNTHESIZED with numpy (no samples copied from
anywhere), so the whole library is free to ship and use — no
copyright, no licence, no download needed. Run this script to
(re)build the `sounds/` folder:

    python generate_sounds.py

The editor's Sounds tab lists these files, lets you listen to them,
and adds them to your video at the playhead.
"""
import os
import wave
from pathlib import Path

import numpy as np

SR = 44100
OUT = Path(__file__).resolve().parent / "sounds"


def _save(name, data):
    data = np.clip(data, -1.0, 1.0)
    pcm = (data * 32767).astype(np.int16)
    path = OUT / (name + ".wav")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())
    print("wrote %s (%.2fs)" % (path.name, len(data) / SR))


def _tone(freq, dur, amp=0.6, decay=6.0):
    t = np.arange(int(dur * SR)) / SR
    env = np.exp(-decay * t)
    return amp * np.sin(2 * np.pi * freq * t) * env


def _sweep(f0, f1, dur, amp=0.6):
    t = np.arange(int(dur * SR)) / SR
    phase = 2 * np.pi * (f0 * t + (f1 - f0) * t * t / (2 * dur))
    return amp * np.sin(phase)


def _noise(dur, amp=0.5, seed=0):
    rng = np.random.default_rng(seed)
    return amp * rng.standard_normal(int(dur * SR))


def _lowpass(x, alpha):
    out = np.zeros_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc = acc + alpha * (v - acc)
        out[i] = acc
    return out


def make_all():
    OUT.mkdir(exist_ok=True)
    # 1. Whoosh — noise with a rising then falling envelope.
    t = np.arange(int(0.7 * SR)) / SR
    env = np.sin(np.pi * np.clip(t / 0.7, 0, 1)) ** 2
    _save("whoosh", _lowpass(_noise(0.7, 0.9, seed=1), 0.08) * env * 1.6)
    # 2. Pop — a short low thump.
    _save("pop", _tone(320, 0.12, amp=0.9, decay=35.0))
    # 3. Ding — bright bell (two harmonics, long ring).
    d = _tone(880, 0.9, amp=0.5, decay=4.0) + _tone(1318, 0.9, amp=0.25, decay=5.0)
    _save("ding", d)
    # 4. Coin — the classic two-note coin (988 then 1319 Hz).
    coin = np.concatenate([_tone(988, 0.09, amp=0.6, decay=8.0),
                           _tone(1319, 0.35, amp=0.6, decay=6.0)])
    _save("coin", coin)
    # 5. Boom — deep impact: 55 Hz sine + noise thump.
    thump = _noise(0.25, 0.5, seed=2) * np.exp(-np.arange(int(0.25 * SR)) / SR * 18)
    boom = _tone(55, 1.0, amp=0.9, decay=3.0)
    boom[:len(thump)] += thump
    _save("boom", boom)
    # 6. Riser — pitch sweeps up and gets louder (build-up before a drop).
    t = np.arange(int(1.0 * SR)) / SR
    riser = _sweep(200, 1400, 1.0, amp=0.5) * np.clip(t / 1.0, 0, 1) ** 1.5
    _save("riser", riser)
    # 7. Airhorn — loud brassy chord with a little wobble.
    t = np.arange(int(0.8 * SR)) / SR
    horn = sum(np.sin(2 * np.pi * f * t) * (1 + 0.06 * np.sin(2 * np.pi * 30 * t))
               for f in (220, 277, 330)) / 3.0
    _save("airhorn", horn * 0.7 * np.minimum(1.0, t * 40) * np.exp(-t * 0.8))
    # 8. Applause — many short noise bursts, like a small crowd.
    rng = np.random.default_rng(3)
    ap = np.zeros(int(1.6 * SR))
    for _ in range(90):
        start = int(rng.uniform(0, 1.2) * SR)
        ln = int(rng.uniform(0.02, 0.06) * SR)
        ap[start:start + ln] += rng.standard_normal(ln) * rng.uniform(0.2, 0.7)
    ap *= np.exp(-np.arange(len(ap)) / SR * 1.2)
    _save("applause", ap * 0.7)
    # 9. Drumroll — fast repeated snare-like hits.
    dr = np.zeros(int(1.0 * SR))
    for i in range(14):
        start = int(i * 0.07 * SR)
        ln = int(0.05 * SR)
        dr[start:start + ln] += _noise(0.05, 0.7, seed=10 + i) * np.exp(-np.arange(ln) / SR * 60)
    _save("drumroll", dr)
    # 10. Click — a tiny UI tick.
    _save("click", _tone(1500, 0.04, amp=0.5, decay=60.0))
    # 11. Laser — a zap that falls in pitch.
    _save("laser", _sweep(1400, 120, 0.4, amp=0.6) * np.exp(-np.arange(int(0.4 * SR)) / SR * 4))
    # 12. Success — a happy 4-note arpeggio (C E G C).
    notes = [523, 659, 784, 1047]
    suc = np.concatenate([_tone(f, 0.16, amp=0.55, decay=5.0) for f in notes])
    _save("success", suc)
    # 13. Record scratch — a quick back-and-forth chirp.
    t = np.arange(int(0.35 * SR)) / SR
    scr = np.sin(2 * np.pi * (900 + 700 * np.sin(2 * np.pi * 14 * t)) * t)
    _save("scratch", scr * 0.5 * np.exp(-t * 3))
    # 14. Sad trombone — the classic "wah wah wah wahhh" (descending).
    trom = np.concatenate([
        _tone(233, 0.25, amp=0.5, decay=2.0), _tone(220, 0.25, amp=0.5, decay=2.0),
        _tone(208, 0.25, amp=0.5, decay=2.0), _tone(196, 0.6, amp=0.55, decay=1.5)])
    _save("sad-trombone", trom)
    # 15. Punch — a short heavy hit for a kill / impact.
    punch = _tone(90, 0.25, amp=0.9, decay=14.0)
    hit = _noise(0.08, 0.6, seed=5) * np.exp(-np.arange(int(0.08 * SR)) / SR * 40)
    punch[:len(hit)] += hit
    _save("punch", punch)


if __name__ == "__main__":
    make_all()
    print("Done. %d sounds in %s" % (len(list(OUT.glob('*.wav'))), OUT))
