"""The sound-effects library is now REAL recordings, not synthesized tones.

This script used to generate the 15 original sounds (whoosh, pop, ding,
coin, boom, riser, airhorn, applause, drumroll, click, laser, success,
scratch, sad-trombone, punch) with numpy. Those pure-tone versions
sounded fake, so they were replaced with real recordings from
Freesound (CC-licensed) in v2.4.1. The full list of what each sound
is and where it came from lives in `sounds/SOURCES.txt`.

This file stays here so old docs and scripts that mention it do not
break, but it no longer generates anything: running it just prints
where the library comes from. If you delete a sound, re-download it
from the source listed in SOURCES.txt (same filename, 44.1 kHz mono
16-bit WAV) instead of re-running a synth.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "sounds"
SOURCES = OUT / "SOURCES.txt"


def main():
    n = len(list(OUT.glob("*.wav"))) if OUT.is_dir() else 0
    print("The sound library is real recordings now (%d WAVs in %s)."
          % (n, OUT))
    print("Sources and licences: %s" % SOURCES)
    print("This script no longer generates sounds. To restore a deleted")
    print("sound, re-download it from the source in SOURCES.txt.")


if __name__ == "__main__":
    main()
