#!/usr/bin/env python3
"""
Hlasový kľúč – príkazový riadok (grafické rozhranie: python app.py)

  python voice_password.py enroll --user david --files a.wav b.wav c.wav
  python voice_password.py verify --user david --files test.wav
  (bez --files sa nahráva z mikrofónu – vyžaduje pip install sounddevice)
"""
import argparse
import sys

import voice_core as vc


def record(seconds=5.0):
    import sounddevice as sd
    input(f"  Stlač ENTER a povedz heslo (max {seconds:.0f} s)...")
    y = sd.rec(int(seconds * vc.SR), samplerate=vc.SR, channels=1, dtype="float32")
    sd.wait()
    return y[:, 0].astype(float)


def get_audio(files, n):
    if files:
        return [vc.load_wav(p) for p in files]
    return [record() for _ in range(n)]


def main():
    p = argparse.ArgumentParser(description="Biometrické heslo pomocou hlasu")
    p.add_argument("command", choices=["enroll", "verify"])
    p.add_argument("--user", required=True)
    p.add_argument("--files", nargs="*")
    p.add_argument("--strictness", type=float, default=1.0)
    a = p.parse_args()

    if a.command == "enroll":
        tpl = vc.build_template(a.user, get_audio(a.files, 3))
        vc.save_template(tpl)
        print(f"Heslo pre '{a.user}' uložené. Prahy: {tpl['thresholds']}")
        for w in tpl["warnings"]:
            print("POZOR:", w)
        return

    tpl = vc.load_template(a.user)
    if not tpl:
        sys.exit(f"Používateľ '{a.user}' nemá platnú šablónu – spusti enroll.")
    r = vc.verify_features(tpl, vc.extract_features(get_audio(a.files[:1] if a.files else None, 1)[0]),
                           a.strictness)
    v, t = r["values"], r["thresholds"]
    print(f"  Zhoda vety (DTW):   {v['content']:.3f}  (prah ≤ {t['content']:.3f})")
    print(f"  Zhoda hlasu:        {v['speaker']:.3f}  (prah ≥ {t['speaker']:.3f})")
    print(f"  Výška hlasu:        {v['f0']:.0f} Hz (ref. {v['f0_ref']:.0f} Hz)")
    print("  >>> PRÍSTUP POVOLENÝ <<<" if r["ok"] else "  >>> PRÍSTUP ZAMIETNUTÝ <<<")
    sys.exit(0 if r["ok"] else 1)


if __name__ == "__main__":
    main()
