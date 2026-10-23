#!/usr/bin/env python3
"""Construit secours.html : l'outil en un seul fichier qui marche sans internet.

Les bibliothèques (pdf.js, tesseract.js), les données OCR en français et une copie
du répertoire ISPF sont mises dans le fichier. Rien n'est téléchargé à l'ouverture.

Usage : python3 construire-secours.py
Relancer de temps en temps pour rafraîchir la copie du répertoire ISPF.
"""
import base64, datetime, gzip, json, pathlib, urllib.request

ICI = pathlib.Path(__file__).parent
CDN = {
    'pdf': 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js',
    'pdfWorker': 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js',
    'tess': 'https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js',
    'worker': 'https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/worker.min.js',
    'core': 'https://cdn.jsdelivr.net/npm/tesseract.js-core@v5.1.1/tesseract-core-simd-lstm.wasm.js',
    'fra': 'https://cdn.jsdelivr.net/npm/@tesseract.js-data/fra/4.0.0_best_int/fra.traineddata.gz',
}
RTE_API = 'https://www.data.gouv.fr/api/1/datasets/repertoire-des-entreprises/'


def get(url):
    with urllib.request.urlopen(url) as r:
        return r.read()


def b64(b):
    return base64.b64encode(b).decode()


def rte():
    meta = json.loads(get(RTE_API))
    res = next(r for r in meta['resources'] if r['format'] == 'csv' and 'export' in r['title'].lower())
    # Seules les colonnes lues par l'outil (n°, nom, sigle, enseigne, radiation) sont gardées, à leur place.
    vus, lignes = set(), []
    for l in get(res['url']).decode('utf-8').split('\n')[1:]:
        f = l.rstrip('\r').split(';')
        if len(f) < 30:
            continue
        g = [''] * 30
        for k in (0, 1, 2, 11, 28, 29):
            g[k] = f[k]
        t = ';'.join(g)
        if t not in vus:
            vus.add(t)
            lignes.append(t)
    return '\n'.join(lignes).encode()


lib = {k: get(u) for k, u in CDN.items()}
date = datetime.date.today().strftime('%d/%m/%Y')
# Fichiers gzip en base64, décompressés par le navigateur ; fra est déjà en gzip.
donnees = {k: b64(gzip.compress(lib[k], 9)) for k in ('pdfWorker', 'worker', 'core')}
donnees['fra'] = b64(lib['fra'])
donnees['rte'] = b64(gzip.compress(rte(), 9))

html = (ICI / 'index.html').read_text()


def remplacer(a, b):
    global html
    assert html.count(a) == 1, a
    html = html.replace(a, b)


remplacer('<title>Factures fret vers Excel</title>', '<title>Factures fret vers Excel (secours)</title>')
remplacer('<h1>Factures fret vers Excel</h1>', '<h1>Factures fret vers Excel – version de secours</h1>')
debut = html.index("  <p>La facture est lue sur cet ordinateur")
fin = html.index('</p>', debut) + 4
html = html[:debut] + (
    "  <p>Version de secours : marche sans internet. La facture est lue sur cet ordinateur : elle n'est envoyée nulle part. "
    f'Répertoire ISPF des numéros TAHITI inclus, copié le {date}.</p>') + html[fin:]
remplacer(f'<script src="{CDN["pdf"]}"></script>', f'<script src="data:text/javascript;base64,{b64(lib["pdf"])}"></script>')
remplacer(f'<script src="{CDN["tess"]}"></script>', f'<script src="data:text/javascript;base64,{b64(lib["tess"])}"></script>')
remplacer(f"pdfjsLib.GlobalWorkerOptions.workerSrc = '{CDN['pdfWorker']}';", '''// Version de secours : bibliothèques et répertoire ISPF sont dans ce fichier, rien n'est téléchargé.
const SECOURS = ''' + json.dumps(donnees) + ''';
const octets = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
const degz = async s => new Uint8Array(await new Response(new Blob([octets(s)]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer());
const url = (b, type = 'text/javascript') => URL.createObjectURL(new Blob([b], { type }));
// Ouvert depuis le disque, un worker ne peut charger aucun autre fichier : le moteur OCR est donc
// un seul bloc (cœur + données « fra » + worker), et la lecture de « fra » est servie depuis ce bloc.
const libs = (async () => {
  pdfjsLib.GlobalWorkerOptions.workerPort = new Worker(url(await degz(SECOURS.pdfWorker)));
  return url(new Blob([await degz(SECOURS.core), `
;const FRA = "${SECOURS.fra}";
self.fetch = (f => (u, o) => /fra\\\\.traineddata/.test(u) ? Promise.resolve(new Response(Uint8Array.from(atob(FRA), c => c.charCodeAt(0)))) : f(u, o))(self.fetch);
`, await degz(SECOURS.worker)]));
})();''')
remplacer("const pdf = await pdfjsLib.getDocument({ data: buf }).promise;",
          "await libs;\n    const pdf = await pdfjsLib.getDocument({ data: buf }).promise;")
remplacer("Tesseract.createWorker('fra')",
          "libs.then(workerPath => Tesseract.createWorker('fra', 1, { workerPath, langPath: 'secours', cacheMethod: 'none', workerBlobURL: false }))")
remplacer('''    const meta = await (await fetch(RTE_API)).json();
    const res = meta.resources.find(r => r.format === 'csv' && /export/i.test(r.title));
    const texte = await (await fetch(res.url)).text();''',
          "    const texte = new TextDecoder().decode(await degz(SECOURS.rte));")

(ICI / 'secours.html').write_text(html)
print(f'secours.html : {len(html) / 1e6:.1f} Mo, répertoire du {date}')
