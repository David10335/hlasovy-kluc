# Ukážkové nahrávky

Nahrávky na vyskúšanie aplikácie bez mikrofónu (v aplikácii *alebo vyber zvukový súbor*, v desktopovej verzii parameter `--files`).
Rovnaké nahrávky sú použité v demo videu `docs/Hlasovy_kluc_demo.mp4`.

| Súbor | Hovoriaci | Veta | Očakávaný výsledok |
|---|---|---|---|
| `1_registracia_a.wav` – `3_registracia_c.wav` | jackson | „four seven two“ | registrácia hesla (3 vzorky) |
| `4_overenie_spravne.wav` | jackson | „four seven two“ | PRÍSTUP POVOLENÝ |
| `5_overenie_ina_veta.wav` | jackson | „one nine five“ | ZAMIETNUTÝ – iná veta |
| `6_overenie_iny_clovek.wav` | yweweler | „four seven two“ | ZAMIETNUTÝ – iný hlas |

Vety sú poskladané zo slov datasetu [Free Spoken Digit Dataset](https://github.com/Jakobovski/free-spoken-digit-dataset)
(licencia [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)), prevzorkované na 16 kHz.

```bash
cd desktop
python voice_password.py enroll --user jackson --files ../samples/1_registracia_a.wav ../samples/2_registracia_b.wav ../samples/3_registracia_c.wav
python voice_password.py verify --user jackson --files ../samples/4_overenie_spravne.wav
```
