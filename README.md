# Hlasový kľúč

Biometrické heslo pomocou hlasu – projekt na predmet BIKS (TUKE).

**Spustenie:** https://david10335.github.io/hlasovy-kluc/

Používateľ 3× vysloví krátku vetu (heslo). Aplikácia z nahrávok vypočíta vlastnosti hlasu
a pri overení rozhodne, či ide o **tú istú vetu** od **toho istého človeka**.

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
