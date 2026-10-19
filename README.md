# Hlasový kľúč

Biometrické heslo pomocou hlasu – projekt na predmet BSB (TUKE).

**Spustenie:** https://david10335.github.io/hlasovy-kluc/

Používateľ 3× vysloví krátku vetu (heslo). Aplikácia z nahrávok vypočíta vlastnosti hlasu
a pri overení rozhodne, či ide o **tú istú vetu** od **toho istého človeka**.

V jednom zariadení môže mať heslo viac ľudí – v karte **Ľudia** sa pridávajú, prepínajú a odstraňujú.

Všetko sa počíta v prehliadači (iPhone, Android, počítač). Nahrávky sa nikam neodosielajú,
šablóna hlasu sa ukladá iba v danom zariadení.

## Ako to funguje

1. **Detekcia reči (VAD)** – energetický detektor odstráni ticho a šum, spracúvajú sa iba rečové rámce (25 ms okno, 10 ms posun).
2. **Obsah vety** – MFCC (c1–c19 + delty, CMN) porovnané algoritmom DTW s pásmom Sakoe-Chiba. Prah sa kalibruje pri registrácii pomocou „falošných“ vzoriek (registračné nahrávky prehrané odzadu).
3. **Odtlačok hlasu** – kepstrá v pásme 60–4000 Hz normalizované voči štatistikám hlasov iných ľudí (Free Spoken Digit Dataset), *statistics pooling* (priemer + smerodajná odchýlka → 32-rozmerný vektor), skóre = kosínusová podobnosť. Postup je inšpirovaný systémami x-vector / ECAPA-TDNN / WeSpeaker, bez neurónovej siete.
4. **Rozhodnutie** – prístup sa povolí iba vtedy, keď sedí veta, hlas, výška hlasu (F0 ± 4 poltóny) aj dĺžka vety.

## Namerané výsledky

Na datasete (vety z 3 slov, 6 hovoriacich, simulované mikrofóny):

| Pokus | Prijaté |
|---|---|
| správny človek, správna veta | 95 % |
| iný človek, rovnaká veta | 2,4 % |
| ten istý človek, iná veta | 1,7 % |

Prah zhody hlasu 0,93 zodpovedá bodu EER na tomto datasete.

## Inštalácia do telefónu

- **iPhone (Safari):** Zdieľať → *Pridať na plochu*
- **Android (Chrome):** ⋮ → *Pridať na plochu* / *Inštalovať aplikáciu*

Aplikácia sa potom otvára na celú obrazovku ako bežná aplikácia.

## Štruktúra repozitára

| Súbor / priečinok | Obsah |
|---|---|
| `index.html` | zostavená webová aplikácia (GitHub Pages) |
| `manifest.webmanifest`, ikony | inštalácia na plochu telefónu |
| `web/core.js` | jadro spracovania reči (VAD, MFCC, DTW, odtlačok hlasu, F0) |
| `web/page.html` | používateľské rozhranie |
| `web/build.py` | zostavenie `index.html`: `python web/build.py` |
| `desktop/` | desktopová verzia v Pythone (`voice_core.py`, `app.py`, `voice_password.py`) |
| `docs/Hlasovy_kluc_dokumentacia.pdf` | dokumentácia semestrálneho projektu |

Repozitár neobsahuje nahrávky hlasu ani šablóny používateľov (biometrické osobné údaje).

## Spustenie zo zdrojových kódov

```bash
git clone https://github.com/David10335/hlasovy-kluc.git
cd hlasovy-kluc
python -m http.server 8000        # webová verzia → http://localhost:8000
```

Desktopová verzia (Python 3, NumPy, SciPy):

```bash
pip install numpy scipy
cd desktop
python app.py                     # otvorí http://127.0.0.1:8765
```

## Autori

Dávid Andrišov, Peter Danko – FEI TUKE, predmet BSB

## Obmedzenia

- **Prehratie nahrávky (replay attack):** systém nerozlíši živý hlas od kvalitnej nahrávky toho istého človeka. Obranou by bola náhodná výzva (používateľ povie vetu, ktorú vygeneruje systém) alebo detekcia živosti (*liveness detection*).
- **Imitácia a deepfake:** rozpoznanie hlasu je založené na spektrálnych štatistikách, nie na neurónovej sieti. Zručný imitátor alebo syntetický hlas môže mať vyššiu šancu na úspech ako bežný útočník.
- **Šum a mikrofón:** v hlučnom prostredí alebo s iným mikrofónom ako pri registrácii je skóre nižšie. Šablóna sa preto ukladá zvlášť pre každé zariadenie.
- **Krátke vety** sa rozlišujú horšie. Odporúča sa veta s 5–6 slovami.
- **Úložisko:** šablóna je v `localStorage` prehliadača. Vymazaním dát prehliadača sa stratí.
