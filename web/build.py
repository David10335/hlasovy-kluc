"""Zostaví index.html (webová aplikácia pre GitHub Pages) z page.html a core.js.
Použitie (z koreňa repozitára):  python web/build.py
"""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
core = open(os.path.join(HERE, 'core.js'), encoding='utf-8').read().replace(
    "if (typeof module !== 'undefined') module.exports = VC;", "")
page = open(os.path.join(HERE, 'page.html'), encoding='utf-8').read().replace('/*CORE*/', core)
cut=page.index('</style>')+len('</style>')
head,body=page[:cut],page[cut:]
head=head.replace('<meta name="claude:viewport-fit-sides" content="cover">\n','')
head=head.replace('<meta name="theme-color" content="#0c1018">',
 '<meta name="theme-color" content="#0c1018" media="(prefers-color-scheme: dark)">\n<meta name="theme-color" content="#f3f5f9" media="(prefers-color-scheme: light)">\n'
 '<meta name="description" content="Biometrické heslo pomocou hlasu – registrácia vety a overenie hovoriaceho priamo v prehliadači.">\n'
 '<link rel="manifest" href="manifest.webmanifest">\n<link rel="apple-touch-icon" href="apple-touch-icon.png">\n<link rel="icon" type="image/png" href="favicon.png">\n'
 '<meta name="apple-mobile-web-app-title" content="Hlasový kľúč">\n<meta name="mobile-web-app-capable" content="yes">')
full=('<!doctype html>\n<html lang="sk">\n<head>\n<meta charset="utf-8">\n'
      '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
      '<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}[hidden]{display:none!important}</style>\n'
      +head+'\n</head>\n<body>'+body+'\n</body>\n</html>\n')
open(os.path.join(ROOT, 'index.html'), 'w', encoding='utf-8').write(full)
