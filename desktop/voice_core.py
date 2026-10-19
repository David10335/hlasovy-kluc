#!/usr/bin/env python3
"""
Biometrické heslo pomocou hlasu – výpočtové jadro (verzia 3)
============================================================
Heslo je PRIJATÉ iba vtedy, keď súčasne platí:

 1. OBSAH  – povedal si tú istú vetu
      MFCC (c1..c19) + delta, odčítaný priemer (CMN), iba rečové úseky (VAD),
      porovnanie DTW s pásmom Sakoe-Chiba. Prah sa kalibruje pri registrácii
      pomocou "falošných" vzoriek (tie isté nahrávky prehrané odzadu).

 2. HLAS   – hovoril si ty (overenie hovoriaceho)
      Postup prevzatý z moderných systémov (x-vector / ECAPA / WeSpeaker),
      ale bez neurónovej siete:
        a) kepstrálne príznaky v pásme 60–4000 Hz (16 koeficientov),
        b) normalizácia voči "pozadiu" – štatistikám hlasov iných ľudí
           (verejný dataset Free Spoken Digit Dataset, 6 hovoriacich,
           3 000 nahrávok), podobne ako UBM / cohort normalizácia,
        c) "statistics pooling": priemer + smerodajná odchýlka cez všetky
           rečové rámce -> vektor 32 čísel = odtlačok hlasu,
        d) šablóna = priemer odtlačkov z registrácie,
        e) skóre = kosínusová podobnosť (1.0 = identické).
      Prah 0,93 zodpovedá bodu EER (FAR = FRR) nameranému na datasete
      (~4 % chyba na 3-slovných vetách) a ďalej sa prispôsobí podľa toho,
      ako konzistentne hovoril používateľ pri registrácii.

 3. Kontroly rozumnosti: výška hlasu F0 (±4 poltóny) a dĺžka vety.

Závislosti: numpy, scipy
"""

import json
import os

import numpy as np
from scipy.fft import dct
from scipy.io import wavfile
from scipy.signal import resample_poly

SR = 16000
FRAME, HOP, N_FFT = 400, 160, 512
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
VERSION = 3

# --- prahy a limity ---
SPK_THR_DEFAULT = 0.93             # EER bod na referenčnom datasete
SPK_THR_RANGE = (0.90, 0.95)
SPK_LOO_MARGIN = 0.05
F0_MAX_SEMITONES = 4.0
DUR_RATIO = (0.6, 1.6)

# --- štatistiky pozadia (FSDD, 84 175 rečových rámcov, 6 hovoriacich) ---
BG_MU = np.array([-1.076, 1.1153, -0.6998, -2.6172, -1.2773, -0.8422, -0.1068, -0.3528,
                  0.1613, 0.0055, 0.0273, -0.2977, -0.0066, -0.2675, 0.0888, -0.1551])
BG_SD = np.array([5.0198, 4.0199, 3.263, 2.3175, 2.4712, 1.6819, 1.6279, 1.2175,
                  1.2684, 1.1139, 1.1223, 0.9221, 0.829, 0.8044, 0.7147, 0.6537])


# ================================================================ audio I/O
def resample(y, from_sr, to_sr=SR):
    if int(from_sr) == int(to_sr):
        return np.asarray(y, dtype=np.float64)
    g = np.gcd(int(from_sr), int(to_sr))
    return resample_poly(np.asarray(y, dtype=np.float64), int(to_sr) // g, int(from_sr) // g)


def load_wav(path, sr=SR):
    file_sr, y = wavfile.read(path)
    if y.dtype.kind in "iu":
        y = y / float(np.iinfo(y.dtype).max)
    y = y.astype(np.float64)
    if y.ndim > 1:
        y = y.mean(axis=1)
    return resample(y, file_sr, sr)


def save_wav(path, y, sr=SR):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    wavfile.write(path, sr, (np.clip(y, -1, 1) * 32767).astype(np.int16))


# ============================================================ predspracovanie
def frames(y, frame=FRAME, hop=HOP):
    if len(y) < frame:
        y = np.pad(y, (0, frame - len(y)))
    n = 1 + (len(y) - frame) // hop
    return y[np.arange(frame)[None, :] + hop * np.arange(n)[:, None]]


def speech_mask(y):
    """Energetický detektor reči (VAD) s odhadom šumu z najtichších rámcov."""
    e = 10 * np.log10((frames(y) ** 2).mean(axis=1) + 1e-12)
    noise, peak = np.percentile(e, 10), np.percentile(e, 99)
    m = e > max(noise + max(6.0, 0.3 * (peak - noise)), peak - 40)
    m = _fill_gaps(m, 20)          # medzery < 200 ms patria k reči
    m = _drop_short(m, 5)          # výkyvy < 50 ms nie sú reč
    return m, peak - noise


def _fill_gaps(m, k):
    out, idx = m.copy(), np.where(m)[0]
    for a, b in zip(idx[:-1], idx[1:]):
        if 1 < b - a <= k:
            out[a:b] = True
    return out


def _drop_short(m, k):
    out, i, n = m.copy(), 0, len(m)
    while i < n:
        if m[i]:
            j = i
            while j < n and m[j]:
                j += 1
            if j - i < k:
                out[i:j] = False
            i = j
        else:
            i += 1
    return out


# ===================================================== extrakcia príznakov
def mel_fb(n_mels, fmin, fmax, sr=SR, n_fft=N_FFT):
    mel = lambda f: 2595 * np.log10(1 + f / 700)
    imel = lambda m: 700 * (10 ** (m / 2595) - 1)
    hz = imel(np.linspace(mel(fmin), mel(fmax), n_mels + 2))
    freqs = np.fft.rfftfreq(n_fft, 1 / sr)
    fb = np.zeros((n_mels, len(freqs)))
    for i in range(n_mels):
        l, c, r = hz[i], hz[i + 1], hz[i + 2]
        fb[i] = np.clip(np.minimum((freqs - l) / (c - l), (r - freqs) / (r - c)), 0, None)
    return fb


FB_CONTENT = mel_fb(40, 60, 7600)   # obsah vety – celé pásmo
FB_SPEAKER = mel_fb(24, 60, 4000)   # hlas – pásmo 60–4000 Hz


def power_spectrum(y):
    pre = np.append(y[0], y[1:] - 0.97 * y[:-1])
    return np.abs(np.fft.rfft(frames(pre) * np.hamming(FRAME), N_FFT)) ** 2


def cepstrum(power, fb, n):
    return dct(np.log(power @ fb.T + 1e-8), type=2, axis=1, norm="ortho")[:, :n]


def delta(x, N=2):
    T = len(x)
    p = np.pad(x, ((N, N), (0, 0)), mode="edge")
    den = 2 * sum(n * n for n in range(1, N + 1))
    return sum(n * (p[N + n:N + n + T] - p[N - n:N - n + T]) for n in range(1, N + 1)) / den


def pitch(y, fmin=70, fmax=400):
    """F0 autokoreláciou s center-clippingom; 0 = neznelý rámec."""
    fr = frames(y, frame=640, hop=HOP)
    fr = fr - fr.mean(axis=1, keepdims=True)
    cl = 0.3 * np.abs(fr).max(axis=1, keepdims=True)
    fr = np.where(fr > cl, fr - cl, np.where(fr < -cl, fr + cl, 0.0)) * np.hanning(640)
    ac = np.fft.irfft(np.abs(np.fft.rfft(fr, 2048)) ** 2)[:, :640]
    ac = ac / (ac[:, :1] + 1e-12)
    lo, hi = int(SR / fmax), int(SR / fmin)
    seg = ac[:, lo:hi]
    best = seg.max(axis=1)
    f0 = np.zeros(len(ac))
    for i in np.where(best >= 0.35)[0]:
        s = seg[i]
        pk = np.where((s[1:-1] > s[:-2]) & (s[1:-1] >= s[2:]) & (s[1:-1] >= 0.85 * best[i]))[0] + 1
        k = float(pk[0] if len(pk) else np.argmax(s))
        ki = int(k)
        if 0 < ki < len(s) - 1:
            a, b, c = s[ki - 1], s[ki], s[ki + 1]
            k += 0.5 * (a - c) / (a - 2 * b + c + 1e-12)
        f0[i] = SR / (k + lo)
    return f0


def speaker_embedding(cep):
    """Statistics pooling: priemer + odchýlka normalizovaných kepstier -> jednotkový vektor."""
    x = (cep - BG_MU) / BG_SD
    e = np.concatenate([x.mean(axis=0), x.std(axis=0)])
    return e / (np.linalg.norm(e) + 1e-12)


def extract_features(y):
    y = np.asarray(y, dtype=np.float64)
    y = y - y.mean()
    if np.max(np.abs(y)) < 1e-4:
        raise ValueError("Nahrávka je úplne tichá – skontroluj mikrofón.")
    y = y / np.max(np.abs(y))

    mask, snr = speech_mask(y)
    n_speech = int(mask.sum())
    if n_speech < 50:
        raise ValueError("Zachytených menej ako 0,5 s reči – hovor bližšie alebo hlasnejšie.")
    if snr < 15:
        raise ValueError(f"Príliš veľa šumu (odstup {snr:.0f} dB) – skús to v tichšom prostredí.")

    power = power_spectrum(y)
    n = min(len(power), len(mask))
    power, mask = power[:n], mask[:n]

    # obsah vety
    cc = cepstrum(power, FB_CONTENT, 20)[mask][:, 1:]
    seq = cc - cc.mean(axis=0)
    seq = np.hstack([seq, delta(seq)])

    # hlas
    cs = cepstrum(power, FB_SPEAKER, 17)[mask][:, 1:]
    emb = speaker_embedding(cs)

    f0 = pitch(y)[:n]
    f0 = np.pad(f0, (0, n - len(f0)))
    f0v = f0[mask & (f0 > 0)]
    if len(f0v) < 10:
        raise ValueError("Nepodarilo sa zmerať výšku hlasu – hovor zreteľnejšie.")

    return {
        "seq": seq.astype(np.float32).tolist(),
        "emb": emb.tolist(),
        "f0": float(np.median(f0v)),
        "speech_sec": n_speech * HOP / SR,
        "snr_db": float(min(snr, 99)),
    }


# ================================================================ porovnanie
def dtw(a, b, band=0.2):
    """DTW s pásmom Sakoe-Chiba, vzdialenosť normalizovaná dĺžkou cesty."""
    a, b = np.asarray(a, np.float64), np.asarray(b, np.float64)
    n, m = len(a), len(b)
    cost = np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).mean(axis=2))
    r = max(int(band * max(n, m)), abs(n - m) + 2)
    D = np.full((n + 1, m + 1), np.inf)
    L = np.zeros((n + 1, m + 1))
    D[0, 0] = 0.0
    for i in range(1, n + 1):
        jc = i * m / n
        for j in range(max(1, int(jc - r)), min(m, int(jc + r) + 1) + 1):
            d, l = D[i - 1, j - 1], L[i - 1, j - 1]
            if D[i - 1, j] < d:
                d, l = D[i - 1, j], L[i - 1, j]
            if D[i, j - 1] < d:
                d, l = D[i, j - 1], L[i, j - 1]
            D[i, j] = d + cost[i - 1, j - 1]
            L[i, j] = l + 1
    return float(D[n, m] / L[n, m]) if np.isfinite(D[n, m]) else 9.9


def mean_embedding(samples):
    e = np.mean([s["emb"] for s in samples], axis=0)
    return e / np.linalg.norm(e)


def compare(test, samples):
    f0_ref = float(np.median([s["f0"] for s in samples]))
    return {
        "content": min(dtw(test["seq"], s["seq"]) for s in samples),
        "speaker": float(np.dot(test["emb"], mean_embedding(samples))),
        "f0": test["f0"],
        "f0_ref": f0_ref,
        "f0_diff": float(abs(12 * np.log2(test["f0"] / f0_ref))),
        "dur_ratio": test["speech_sec"] / float(np.median([s["speech_sec"] for s in samples])),
    }


# ================================================================ registrácia
def build_template(user, audios):
    if len(audios) < 3:
        raise ValueError("Na registráciu treba aspoň 3 nahrávky.")
    feats = [extract_features(y) for y in audios]
    gen = [compare(feats[i], feats[:i] + feats[i + 1:]) for i in range(len(feats))]
    rev = [compare(extract_features(np.asarray(y)[::-1]), feats) for y in audios]
    calib = {
        "genuine_content": [r["content"] for r in gen],
        "reversed_content": [r["content"] for r in rev],
        "genuine_speaker": [r["speaker"] for r in gen],
    }
    thresholds, warnings = compute_thresholds(calib)
    return {"user": user, "version": VERSION, "thresholds": thresholds,
            "calibration": calib, "samples": feats, "warnings": warnings}


def compute_thresholds(calib):
    warnings = []
    g_c = max(calib["genuine_content"])
    n_c = min(calib["reversed_content"])
    if n_c > g_c:
        t_content = g_c + 0.4 * (n_c - g_c)
        if (n_c - g_c) / n_c < 0.25:
            warnings.append("Veta je krátka alebo jednoduchá – zvoľ dlhšiu (aspoň 5–6 slov).")
    else:
        t_content = g_c * 1.1
        warnings.append("Registračné nahrávky sa medzi sebou veľmi líšia – "
                        "povedz vetu vždy rovnako a v tichu.")

    loo = min(calib["genuine_speaker"])
    t_spk = float(np.clip(loo - SPK_LOO_MARGIN, *SPK_THR_RANGE))
    if loo < SPK_THR_RANGE[0] + SPK_LOO_MARGIN:
        warnings.append("Hlas sa medzi registračnými nahrávkami výrazne menil – "
                        "hovor rovnakým tónom a v rovnakej vzdialenosti od mikrofónu.")
    return {"content": t_content, "speaker": t_spk, "f0": F0_MAX_SEMITONES}, warnings


def verify_features(tpl, feat, strictness=1.0):
    """strictness 1.0 = štandard; <1 prísnejšie; >1 benevolentnejšie."""
    s = float(strictness)
    r = compare(feat, tpl["samples"])
    base = tpl["thresholds"]
    t = {
        "content": base["content"] * s,
        "speaker": 1 - (1 - base["speaker"]) * s,
        "f0": base["f0"] * s,
    }
    lo, hi = DUR_RATIO
    checks = {
        "content": r["content"] <= t["content"],
        "speaker": r["speaker"] >= t["speaker"],
        "f0": r["f0_diff"] <= t["f0"],
        "duration": lo / s <= r["dur_ratio"] <= hi * s,
    }
    return {"ok": all(checks.values()), "checks": checks, "values": r, "thresholds": t}


# ================================================================ úložisko
def template_path(user):
    return os.path.join(TEMPLATE_DIR, f"{user}.json")


def save_template(tpl):
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    with open(template_path(tpl["user"]), "w", encoding="utf-8") as f:
        json.dump(tpl, f)


def load_template(user):
    p = template_path(user)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        tpl = json.load(f)
    if tpl.get("version") != VERSION:
        return None
    tpl["thresholds"], tpl["warnings"] = compute_thresholds(tpl["calibration"])
    return tpl


def template_status(user):
    p = template_path(user)
    if not os.path.exists(p):
        return "none"
    return "ok" if load_template(user) else "outdated"


def list_users():
    if not os.path.isdir(TEMPLATE_DIR):
        return []
    return sorted(f[:-5] for f in os.listdir(TEMPLATE_DIR) if f.endswith(".json"))
