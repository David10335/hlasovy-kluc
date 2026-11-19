# Hlasový kľúč – biometrické heslo pomocou hlasu

Semestrálny projekt na predmet **BSB**, Fakulta elektrotechniky a informatiky, Technická univerzita v Košiciach (2026).

**Autori:** Dávid Andrišov, Peter Danko

| | |
|---|---|
| **Aplikácia (online)** | https://david10335.github.io/hlasovy-kluc/ |
| **Zdrojový kód** | https://github.com/David10335/hlasovy-kluc |
| **Dokumentácia** | [`docs/Hlasovy_kluc_dokumentacia.pdf`](docs/Hlasovy_kluc_dokumentacia.pdf) |
| **Demo video** | [`docs/Hlasovy_kluc_demo.mp4`](docs/Hlasovy_kluc_demo.mp4) |

## Zadanie

Používateľ nahrá krátku vetu, program zistí základné vlastnosti hlasu a porovná ich s ďalšou nahrávkou.
Výsledkom je rozhodnutie, či je heslo správne alebo nie.

Riešenie overuje **dve veci naraz**: či zaznela **tá istá veta** a či ju povedal **ten istý človek**.
Nestačí teda poznať heslo – musí ho povedať človek, ktorý ho zaregistroval.

## Ako to funguje

1. **Registrácia** – používateľ 3× vysloví zvolenú vetu. Z nahrávok sa vytvorí šablóna a prahy sa nakalibrujú pre daného človeka.
2. **Detekcia reči (VAD)** – energetický detektor odstráni ticho, spracúvajú sa iba rečové rámce (25 ms okno, 10 ms posun, 16 kHz).
3. **Obsah vety** – MFCC (c1–c19 + delty, odčítanie priemeru) porovnané algoritmom DTW s pásmom Sakoe-Chiba.
   Prah sa kalibruje pomocou „falošných“ vzoriek – registračných nahrávok prehraných odzadu.
4. **Odtlačok hlasu** – kepstrá v pásme 60–4000 Hz normalizované voči hlasom iných ľudí (Free Spoken Digit Dataset),
   *statistics pooling* (priemer + smerodajná odchýlka → 32-rozmerný vektor), skóre = kosínusová podobnosť.
   Postup je inšpirovaný systémami x-vector / ECAPA-TDNN, bez neurónovej siete.
5. **Rozhodnutie** – prístup sa povolí iba vtedy, keď sedí veta, hlas, výška hlasu (F0 ± 4 poltóny) aj dĺžka vety.
   Pri zamietnutí aplikácia uvedie dôvod (iná veta / iný hlas …).

Všetko sa počíta v zariadení používateľa. Nahrávky sa nikam neodosielajú, šablóna obsahuje iba odvodené príznaky (nie zvuk).

## Výsledky

Vyhodnotenie na 2 592 overeniach (vety z 3 slov, 6 hovoriacich, simulované rôzne mikrofóny):

| Skupina pokusov | Počet | Prijaté |
|---|---:|---:|
| správny človek, správna veta | 144 | 95,1 % |
| správny človek, iná veta | 288 | 1,7 % |
| iný človek, rovnaká veta (útočník pozná heslo) | 720 | 2,4 % |
| iný človek, iná veta | 1 440 | 0,0 % |

Samotné overenie hlasu dosahuje mieru rovnakej chyby **EER ≈ 3,5 %**. Overenie jednej nahrávky trvá 0,05–0,1 s.
Podrobné vyhodnotenie je v dokumentácii (kapitola 4).

## Demo video

[`docs/Hlasovy_kluc_demo.mp4`](docs/Hlasovy_kluc_demo.mp4) (77 s) ukazuje webovú aplikáciu v prehliadači:
pridanie človeka, registráciu hesla, úspešné overenie, zamietnutie inej vety a zamietnutie iného človeka so správnou vetou.
Ako vstup mikrofónu sú v ňom použité nahrávky z priečinka [`samples/`](samples/) (Free Spoken Digit Dataset), ktoré sú vo videu aj počuť.

## Spustenie

### Webová aplikácia (odporúčané)

Stačí otvoriť https://david10335.github.io/hlasovy-kluc/ v prehliadači (Chrome, Edge, Firefox, Safari) a povoliť mikrofón.

- **iPhone (Safari):** Zdieľať → *Pridať na plochu*
- **Android (Chrome):** ⋮ → *Inštalovať aplikáciu*

Lokálne zo zdrojových kódov:

```bash
git clone https://github.com/David10335/hlasovy-kluc.git
cd hlasovy-kluc
python -m http.server 8000        # potom otvoriť http://localhost:8000
```

Po zmene `web/core.js` alebo `web/page.html` sa `index.html` zostaví príkazom `python web/build.py`.

### Desktopová verzia (Python)

Rovnaký algoritmus v jazyku Python s lokálnym serverom. Vyžaduje Python 3 a knižnice NumPy a SciPy.

```bash
pip install numpy scipy
cd desktop
python app.py                     # otvorí http://127.0.0.1:8765
```

Príkazový riadok (napr. s ukážkovými nahrávkami):

```bash
cd desktop
python voice_password.py enroll --user jackson --files ../samples/1_registracia_a.wav ../samples/2_registracia_b.wav ../samples/3_registracia_c.wav
python voice_password.py verify --user jackson --files ../samples/4_overenie_spravne.wav     # PRÍSTUP POVOLENÝ
python voice_password.py verify --user jackson --files ../samples/6_overenie_iny_clovek.wav  # PRÍSTUP ZAMIETNUTÝ
```

## Používanie

1. V paneli **Ľudia** napíšte meno a kliknite na **Pridať**.
2. Na karte **Registrácia** ťuknite na mikrofón a 3× povedzte vetu s 5–6 slovami, vždy rovnako. Nahrávanie sa zastaví samo.
3. Na karte **Overenie** ťuknite na mikrofón a povedzte heslo. Zobrazí sa **PRÍSTUP POVOLENÝ** alebo **PRÍSTUP ZAMIETNUTÝ** s hodnotami a prahmi.
4. Posuvník **Prísnosť** prepočíta posledný pokus s prísnejšími alebo voľnejšími prahmi.
5. Namiesto mikrofónu možno použiť zvukový súbor (*alebo vyber zvukový súbor*), napr. z priečinka `samples/`.

Podrobná príručka a riešenie problémov sú v dokumentácii (kapitola 5).

## Štruktúra repozitára

| Súbor / priečinok | Obsah |
|---|---|
| `index.html` | zostavená webová aplikácia (GitHub Pages) |
| `manifest.webmanifest`, ikony | inštalácia na plochu telefónu |
| `web/core.js` | jadro spracovania reči (VAD, MFCC, DTW, odtlačok hlasu, F0) |
| `web/page.html` | používateľské rozhranie |
| `web/build.py` | zostavenie `index.html` |
| `desktop/voice_core.py` | algoritmus v Pythone |
| `desktop/app.py` | lokálny server desktopovej verzie |
| `desktop/voice_password.py` | príkazový riadok |
| `desktop/web/index.html` | rozhranie desktopovej verzie |
| `samples/` | ukážkové nahrávky na vyskúšanie |
| `docs/` | dokumentácia (PDF) a demo video |

Repozitár neobsahuje nahrávky hlasu ani šablóny autorov (biometrické osobné údaje).

## Obmedzenia

- **Prehratie nahrávky (replay):** systém nerozlíši živý hlas od kvalitnej nahrávky toho istého človeka. Obranou by bola náhodná výzva alebo detekcia živosti.
- **Imitácia a syntetický hlas:** odtlačok hlasu je založený na spektrálnych štatistikách, nie na neurónovej sieti.
- **Šum a mikrofón:** v hlučnom prostredí alebo s iným mikrofónom ako pri registrácii je skóre nižšie; šablóna sa ukladá zvlášť pre každé zariadenie.
- **Krátke vety** sa rozlišujú horšie – odporúča sa veta s 5–6 slovami.
- **Úložisko:** šablóna je v `localStorage` prehliadača; vymazaním dát prehliadača sa stratí.

Aplikácia je demonštráciou princípov hlasovej biometrie, nie náhradou bezpečnej autentifikácie.
