/* =====================================================================
   Hlasový kľúč – výpočtové jadro v JavaScripte (port voice_core.py v3)
   Všetko beží lokálne v prehliadači, nič sa neodosiela na server.
   ===================================================================== */
const VC = (() => {
  const SR = 16000, FRAME = 400, HOP = 160, NFFT = 512;
  const SPK_THR_RANGE = [0.90, 0.95], SPK_LOO_MARGIN = 0.05, F0_MAX = 4.0, DUR = [0.6, 1.6];
  const BG_MU = [-1.076, 1.1153, -0.6998, -2.6172, -1.2773, -0.8422, -0.1068, -0.3528,
    0.1613, 0.0055, 0.0273, -0.2977, -0.0066, -0.2675, 0.0888, -0.1551];
  const BG_SD = [5.0198, 4.0199, 3.263, 2.3175, 2.4712, 1.6819, 1.6279, 1.2175,
    1.2684, 1.1139, 1.1223, 0.9221, 0.829, 0.8044, 0.7147, 0.6537];

  /* ---------------- FFT (radix-2, in-place) ---------------- */
  const fftCache = {};
  function fftTables(n) {
    if (fftCache[n]) return fftCache[n];
    const rev = new Uint32Array(n), bits = Math.log2(n);
    for (let i = 0; i < n; i++) { let r = 0; for (let b = 0; b < bits; b++) r |= ((i >> b) & 1) << (bits - 1 - b); rev[i] = r; }
    const cos = new Float64Array(n / 2), sin = new Float64Array(n / 2);
    for (let i = 0; i < n / 2; i++) { cos[i] = Math.cos(2 * Math.PI * i / n); sin[i] = -Math.sin(2 * Math.PI * i / n); }
    return (fftCache[n] = {rev, cos, sin});
  }
  // vráti výkonové spektrum |X|^2 (n/2+1 hodnôt) reálneho signálu x (dĺžka <= n, doplní nulami)
  function powerSpec(x, n) {
    const {rev, cos, sin} = fftTables(n);
    const re = new Float64Array(n), im = new Float64Array(n);
    for (let i = 0; i < x.length && i < n; i++) re[rev[i]] = x[i];
    for (let size = 2; size <= n; size <<= 1) {
      const half = size >> 1, step = n / size;
      for (let s = 0; s < n; s += size) for (let k = 0; k < half; k++) {
        const c = cos[k * step], sn = sin[k * step], a = s + k, b = a + half;
        const tr = re[b] * c - im[b] * sn, ti = re[b] * sn + im[b] * c;
        re[b] = re[a] - tr; im[b] = im[a] - ti; re[a] += tr; im[a] += ti;
      }
    }
    const out = new Float64Array(n / 2 + 1);
    for (let i = 0; i <= n / 2; i++) out[i] = re[i] * re[i] + im[i] * im[i];
    return out;
  }
  // inverzná FFT reálneho symetrického výkonového spektra -> autokorelácia (prvých m hodnôt)
  function irfftReal(P, n, m) {
    const {rev, cos, sin} = fftTables(n);
    const re = new Float64Array(n), im = new Float64Array(n);
    for (let i = 0; i < n; i++) { const k = i <= n / 2 ? i : n - i; re[rev[i]] = P[k]; }
    for (let size = 2; size <= n; size <<= 1) {
      const half = size >> 1, step = n / size;
      for (let s = 0; s < n; s += size) for (let k = 0; k < half; k++) {
        const c = cos[k * step], sn = -sin[k * step], a = s + k, b = a + half;
        const tr = re[b] * c - im[b] * sn, ti = re[b] * sn + im[b] * c;
        re[b] = re[a] - tr; im[b] = im[a] - ti; re[a] += tr; im[a] += ti;
      }
    }
    const out = new Float64Array(m);
    for (let i = 0; i < m; i++) out[i] = re[i] / n;
    return out;
  }

  /* ---------------- pomocné ---------------- */
  const hamming = n => Float64Array.from({length: n}, (_, i) => 0.54 - 0.46 * Math.cos(2 * Math.PI * i / (n - 1)));
  const hanning = n => Float64Array.from({length: n}, (_, i) => 0.5 - 0.5 * Math.cos(2 * Math.PI * i / (n - 1)));
  const HAMM = hamming(FRAME), HANN640 = hanning(640);
  function percentile(arr, q) {
    const a = Float64Array.from(arr).sort(), pos = (a.length - 1) * q / 100, lo = Math.floor(pos);
    return lo + 1 < a.length ? a[lo] + (a[lo + 1] - a[lo]) * (pos - lo) : a[lo];
  }
  const median = a => percentile(a, 50);
  function nFrames(len, frame = FRAME, hop = HOP) { return 1 + Math.floor((Math.max(len, frame) - frame) / hop); }
  function frameAt(y, i, frame = FRAME, hop = HOP) {
    const f = new Float64Array(frame), o = i * hop;
    for (let k = 0; k < frame; k++) f[k] = o + k < y.length ? y[o + k] : 0;
    return f;
  }

  function melFb(nMels, fmin, fmax) {
    const mel = f => 2595 * Math.log10(1 + f / 700), imel = m => 700 * (Math.pow(10, m / 2595) - 1);
    const a = mel(fmin), b = mel(fmax), hz = [];
    for (let i = 0; i < nMels + 2; i++) hz.push(imel(a + (b - a) * i / (nMels + 1)));
    const nb = NFFT / 2 + 1, fb = [];
    for (let i = 0; i < nMels; i++) {
      const row = new Float64Array(nb), l = hz[i], c = hz[i + 1], r = hz[i + 2];
      for (let k = 0; k < nb; k++) { const f = k * SR / NFFT; row[k] = Math.max(0, Math.min((f - l) / (c - l), (r - f) / (r - c))); }
      fb.push(row);
    }
    return fb;
  }
  const FB_CONTENT = melFb(40, 60, 7600), FB_SPEAKER = melFb(24, 60, 4000);
  function dctOrtho(x, nOut) {
    const N = x.length, out = new Float64Array(nOut);
    for (let k = 0; k < nOut; k++) {
      let s = 0; for (let n = 0; n < N; n++) s += x[n] * Math.cos(Math.PI * k * (2 * n + 1) / (2 * N));
      out[k] = 2 * s * (k === 0 ? Math.sqrt(1 / (4 * N)) : Math.sqrt(1 / (2 * N)));
    }
    return out;
  }
  function cep(power, fb, n) {
    const lm = new Float64Array(fb.length);
    for (let m = 0; m < fb.length; m++) { let s = 0; const row = fb[m]; for (let k = 0; k < row.length; k++) s += power[k] * row[k]; lm[m] = Math.log(s + 1e-8); }
    return dctOrtho(lm, n);
  }

  /* ---------------- VAD ---------------- */
  function speechMask(y) {
    const n = nFrames(y.length), e = new Float64Array(n);
    for (let i = 0; i < n; i++) { let s = 0; const o = i * HOP; for (let k = 0; k < FRAME; k++) { const v = o + k < y.length ? y[o + k] : 0; s += v * v; } e[i] = 10 * Math.log10(s / FRAME + 1e-12); }
    const noise = percentile(e, 10), peak = percentile(e, 99);
    const thr = Math.max(noise + Math.max(6, 0.3 * (peak - noise)), peak - 40);
    let m = Array.from(e, v => v > thr);
    // vyplniť medzery <= 20 rámcov
    const idx = []; m.forEach((v, i) => v && idx.push(i));
    for (let j = 0; j + 1 < idx.length; j++) { const a = idx[j], b = idx[j + 1]; if (b - a > 1 && b - a <= 20) for (let i = a; i < b; i++) m[i] = true; }
    // zahodiť úseky < 5 rámcov
    for (let i = 0; i < n;) { if (m[i]) { let j = i; while (j < n && m[j]) j++; if (j - i < 5) for (let k = i; k < j; k++) m[k] = false; i = j; } else i++; }
    return {mask: m, snr: peak - noise};
  }

  /* ---------------- výška hlasu ---------------- */
  function pitch(y) {
    const n = nFrames(y.length, 640, HOP), f0 = new Float64Array(n);
    const lo = Math.floor(SR / 400), hi = Math.floor(SR / 70);
    for (let i = 0; i < n; i++) {
      const fr = frameAt(y, i, 640, HOP); let mean = 0;
      for (let k = 0; k < 640; k++) mean += fr[k]; mean /= 640;
      let mx = 0; for (let k = 0; k < 640; k++) { fr[k] -= mean; mx = Math.max(mx, Math.abs(fr[k])); }
      const cl = 0.3 * mx;
      for (let k = 0; k < 640; k++) { const v = fr[k]; fr[k] = (v > cl ? v - cl : v < -cl ? v + cl : 0) * HANN640[k]; }
      const ac = irfftReal(powerSpec(fr, 2048), 2048, 640), a0 = ac[0] + 1e-12;
      const seg = []; let best = -Infinity;
      for (let k = lo; k < hi; k++) { const v = ac[k] / a0; seg.push(v); if (v > best) best = v; }
      if (best < 0.35) continue;
      let k = -1;
      for (let j = 1; j < seg.length - 1; j++) if (seg[j] > seg[j - 1] && seg[j] >= seg[j + 1] && seg[j] >= 0.85 * best) { k = j; break; }
      if (k < 0) k = seg.indexOf(best);
      let kf = k;
      if (k > 0 && k < seg.length - 1) { const a = seg[k - 1], b = seg[k], c = seg[k + 1]; kf += 0.5 * (a - c) / (a - 2 * b + c + 1e-12); }
      f0[i] = SR / (kf + lo);
    }
    return f0;
  }

  /* ---------------- príznaky ---------------- */
  function delta(x, N = 2) {
    const T = x.length, D = x[0].length, den = 2 * (1 + 4), out = [];
    for (let t = 0; t < T; t++) {
      const r = new Float64Array(D);
      for (let n = 1; n <= N; n++) {
        const a = x[Math.min(T - 1, t + n)], b = x[Math.max(0, t - n)];
        for (let d = 0; d < D; d++) r[d] += n * (a[d] - b[d]);
      }
      for (let d = 0; d < D; d++) r[d] /= den;
      out.push(r);
    }
    return out;
  }
  function extract(yIn) {
    const y = Float64Array.from(yIn);
    let mean = 0; for (const v of y) mean += v; mean /= y.length;
    let mx = 0; for (let i = 0; i < y.length; i++) { y[i] -= mean; mx = Math.max(mx, Math.abs(y[i])); }
    if (mx < 1e-4) throw new Error('Nahrávka je úplne tichá – skontroluj mikrofón.');
    for (let i = 0; i < y.length; i++) y[i] /= mx;

    const {mask, snr} = speechMask(y);
    const nSpeech = mask.filter(Boolean).length;
    if (nSpeech < 50) throw new Error('Zachytilo sa menej ako pol sekundy reči – hovor bližšie alebo hlasnejšie.');
    if (snr < 15) throw new Error(`Príliš veľa šumu (odstup ${snr.toFixed(0)} dB) – skús to v tichšom prostredí.`);

    const pre = new Float64Array(y.length); pre[0] = y[0];
    for (let i = 1; i < y.length; i++) pre[i] = y[i] - 0.97 * y[i - 1];
    const n = Math.min(nFrames(y.length), mask.length);
    const cc = [], cs = [];
    for (let i = 0; i < n; i++) {
      if (!mask[i]) continue;
      const fr = frameAt(pre, i); for (let k = 0; k < FRAME; k++) fr[k] *= HAMM[k];
      const P = powerSpec(fr, NFFT);
      cc.push(cep(P, FB_CONTENT, 20).slice(1));
      cs.push(cep(P, FB_SPEAKER, 17).slice(1));
    }
    // obsah: CMN + delty
    const D = cc[0].length, mu = new Float64Array(D);
    for (const r of cc) for (let d = 0; d < D; d++) mu[d] += r[d] / cc.length;
    const seq0 = cc.map(r => r.map((v, d) => v - mu[d]));
    const dl = delta(seq0);
    const seq = seq0.map((r, t) => Array.from(r).concat(Array.from(dl[t])).map(v => Math.fround(v)));
    // hlas: statistics pooling
    const S = 16, m1 = new Float64Array(S), m2 = new Float64Array(S);
    for (const r of cs) for (let d = 0; d < S; d++) { const z = (r[d] - BG_MU[d]) / BG_SD[d]; m1[d] += z; m2[d] += z * z; }
    const emb = [];
    for (let d = 0; d < S; d++) emb.push(m1[d] / cs.length);
    for (let d = 0; d < S; d++) { const mm = m1[d] / cs.length; emb.push(Math.sqrt(Math.max(0, m2[d] / cs.length - mm * mm))); }
    const nrm = Math.hypot(...emb); for (let d = 0; d < emb.length; d++) emb[d] /= nrm + 1e-12;

    const f0 = pitch(y), f0v = [];
    for (let i = 0; i < n; i++) if (mask[i] && i < f0.length && f0[i] > 0) f0v.push(f0[i]);
    if (f0v.length < 10) throw new Error('Nepodarilo sa zmerať výšku hlasu – hovor zreteľnejšie.');
    return {seq, emb, f0: median(f0v), speech_sec: nSpeech * HOP / SR, snr_db: Math.min(snr, 99)};
  }

  /* ---------------- porovnanie ---------------- */
  function dtw(a, b, band = 0.2) {
    const n = a.length, m = b.length, dim = a[0].length;
    const r = Math.max(Math.floor(band * Math.max(n, m)), Math.abs(n - m) + 2);
    let Dp = new Float64Array(m + 1).fill(Infinity), Lp = new Float64Array(m + 1);
    Dp[0] = 0;
    for (let i = 1; i <= n; i++) {
      const Dc = new Float64Array(m + 1).fill(Infinity), Lc = new Float64Array(m + 1);
      const jc = i * m / n, j0 = Math.max(1, Math.floor(jc - r)), j1 = Math.min(m, Math.floor(jc + r) + 1);
      const ai = a[i - 1];
      for (let j = j0; j <= j1; j++) {
        const bj = b[j - 1]; let s = 0;
        for (let d = 0; d < dim; d++) { const t = ai[d] - bj[d]; s += t * t; }
        const c = Math.sqrt(s / dim);
        let d0 = Dp[j - 1], l0 = Lp[j - 1];
        if (Dp[j] < d0) { d0 = Dp[j]; l0 = Lp[j]; }
        if (Dc[j - 1] < d0) { d0 = Dc[j - 1]; l0 = Lc[j - 1]; }
        Dc[j] = d0 + c; Lc[j] = l0 + 1;
      }
      Dp = Dc; Lp = Lc;
    }
    return isFinite(Dp[m]) ? Dp[m] / Lp[m] : 9.9;
  }
  function meanEmb(samples) {
    const e = new Array(samples[0].emb.length).fill(0);
    for (const s of samples) s.emb.forEach((v, i) => e[i] += v / samples.length);
    const n = Math.hypot(...e); return e.map(v => v / n);
  }
  function compare(t, samples) {
    const me = meanEmb(samples), f0ref = median(samples.map(s => s.f0));
    return {
      content: Math.min(...samples.map(s => dtw(t.seq, s.seq))),
      speaker: t.emb.reduce((a, v, i) => a + v * me[i], 0),
      f0: t.f0, f0_ref: f0ref, f0_diff: Math.abs(12 * Math.log2(t.f0 / f0ref)),
      dur_ratio: t.speech_sec / median(samples.map(s => s.speech_sec)),
    };
  }
  function computeThresholds(cal) {
    const w = [];
    const gC = Math.max(...cal.genuine_content), nC = Math.min(...cal.reversed_content);
    let tC;
    if (nC > gC) { tC = gC + 0.4 * (nC - gC); if ((nC - gC) / nC < 0.25) w.push('Veta je krátka alebo jednoduchá – zvoľ dlhšiu (aspoň 5–6 slov).'); }
    else { tC = gC * 1.1; w.push('Registračné nahrávky sa medzi sebou veľmi líšia – povedz vetu vždy rovnako a v tichu.'); }
    const loo = Math.min(...cal.genuine_speaker);
    const tS = Math.min(SPK_THR_RANGE[1], Math.max(SPK_THR_RANGE[0], loo - SPK_LOO_MARGIN));
    if (loo < SPK_THR_RANGE[0] + SPK_LOO_MARGIN) w.push('Hlas sa medzi registračnými nahrávkami výrazne menil – hovor rovnakým tónom a v rovnakej vzdialenosti od mikrofónu.');
    return {thresholds: {content: tC, speaker: tS, f0: F0_MAX}, warnings: w};
  }
  function buildTemplate(user, audios) {
    if (audios.length < 3) throw new Error('Na registráciu treba aspoň 3 nahrávky.');
    const feats = audios.map(extract);
    const gen = feats.map((f, i) => compare(f, feats.filter((_, j) => j !== i)));
    const rev = audios.map(y => compare(extract(Float64Array.from(y).reverse()), feats));
    const calibration = {
      genuine_content: gen.map(r => r.content), reversed_content: rev.map(r => r.content),
      genuine_speaker: gen.map(r => r.speaker),
    };
    const {thresholds, warnings} = computeThresholds(calibration);
    return {user, version: 3, created: Date.now(), thresholds, calibration, samples: feats, warnings};
  }
  function verify(tpl, feat, s = 1) {
    const r = compare(feat, tpl.samples), b = tpl.thresholds;
    const t = {content: b.content * s, speaker: 1 - (1 - b.speaker) * s, f0: b.f0 * s};
    const checks = {
      content: r.content <= t.content, speaker: r.speaker >= t.speaker, f0: r.f0_diff <= t.f0,
      duration: DUR[0] / s <= r.dur_ratio && r.dur_ratio <= DUR[1] * s,
    };
    return {ok: Object.values(checks).every(Boolean), checks, values: r, thresholds: t};
  }
  return {SR, extract, compare, buildTemplate, computeThresholds, verify, dtw};
})();
if (typeof module !== 'undefined') module.exports = VC;
