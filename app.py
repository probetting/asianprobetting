import re

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify

from asian_parse import parse_asian

app = Flask(__name__)

URLS = {'live': 'https://www.asianbetsoccer.com/livescore.html',
        'next': 'https://www.asianbetsoccer.com/nextgame.html'}
HDR = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
       'Accept-Language': 'en-US,en;q=0.9'}


def build(pages):
    """pages = {'live': html, 'next': html} -> {'matches': [...], 'errors': {...}}"""
    matches, errors = [], {}
    for kind, html in pages.items():
        soup = BeautifulSoup(html, 'lxml')
        if not soup.find('table', id='tablematch1'):
            errors[kind] = f'tabelle non trovate ({len(html)} byte)'
            continue
        ms = parse_asian(soup)
        if not ms:
            n1 = len(soup.find('table', id='tablematch1').find_all('tr'))
            n2 = len(soup.find('table', id='tablematch2').find_all('tr')) if soup.find('table', id='tablematch2') else 0
            errors[kind] = f'tabelle vuote (righe {n1}/{n2}, {len(html)} byte)'
        for m in ms:
            m['kind'] = kind
            matches.append(m)
    return {'matches': matches, 'errors': errors}


def fetch_all():
    pages, errors = {}, {}
    for kind, url in URLS.items():
        try:
            r = requests.get(url, headers=HDR, timeout=20)
            pages[kind] = r.text
            if r.status_code != 200:
                errors[kind] = f'HTTP {r.status_code}'
        except Exception as e:
            errors[kind] = str(e)[:120]
    d = build(pages)
    d['errors'] = {**errors, **d['errors']}
    return d


@app.route('/api/refresh')
def refresh():
    resp = jsonify(fetch_all())
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.route('/api/debug')
def debug():
    """Diagnostica: mostra cosa riceve il server e dove la pagina prende i dati."""
    out = {}
    for kind, url in URLS.items():
        try:
            r = requests.get(url, headers=HDR, timeout=20)
            t = r.text
            i = t.find('id="tablematch1"')
            out[kind] = dict(
                status=r.status_code, bytes=len(t),
                tabella=t[max(i - 20, 0):i + 500] if i >= 0 else None,
                script_src=re.findall(r'<script[^>]+src=["\']([^"\']+)', t)[:15],
                url_nei_script=sorted(set(re.findall(r'["\'](/?[\w./-]+\.(?:php|json|aspx|ashx|txt|xml)[^"\']{0,60})["\']', t)))[:25])
        except Exception as e:
            out[kind] = {'errore': str(e)[:150]}
    return jsonify(out)


@app.route('/api/debug2')
def debug2():
    """Cerca nei file JavaScript del sito da dove prende i dati la tabella."""
    from urllib.parse import urljoin
    pat = re.compile(r'ajax|\.get\(|\.post\(|getJSON|fetch\(|XMLHttpRequest|WebSocket|EventSource|\.php|\.aspx|\.ashx|\.json', re.I)
    out = {}
    base = URLS['live']
    try:
        page = requests.get(base, headers=HDR, timeout=20).text
        files = [s for s in re.findall(r'<script[^>]+src=["\']([^"\']+)', page) if s.startswith('/') and 'cookie' not in s.lower()]
        for f in files:
            js = requests.get(urljoin(base, f), headers=HDR, timeout=20).text
            hits, end = [], 0
            for m in pat.finditer(js):
                if m.start() < end:
                    continue
                a, end = max(m.start() - 120, 0), m.end() + 120
                hits.append(js[a:end])
                if len(hits) >= 12:
                    break
            out[f] = dict(bytes=len(js), tracce=hits)
    except Exception as e:
        out['errore'] = str(e)[:150]
    return jsonify(out)


@app.route('/api/debug3')
def debug3():
    """Cerca nella pagina i blocchi grandi che potrebbero contenere i dati dei match."""
    page = requests.get(URLS['live'], headers=HDR, timeout=20).text
    cand = []
    for m in re.finditer(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', page, re.S):
        if len(m.group(1)) > 300:
            cand.append(('script', m.start(), m.group(1)))
    for m in re.finditer(r'"([^"\n]{1500,})"|\'([^\'\n]{1500,})\'', page):
        cand.append(('stringa lunga', m.start(), m.group(1) or m.group(2)))
    for m in re.finditer(r'<textarea[^>]*>(.*?)</textarea>', page, re.S):
        if len(m.group(1)) > 300:
            cand.append(('textarea', m.start(), m.group(1)))
    for m in re.finditer(r'<input[^>]*value=["\']([^"\']{300,})', page):
        cand.append(('input nascosto', m.start(), m.group(1)))
    cand.sort(key=lambda c: -len(c[2]))
    return jsonify(dict(
        bytes=len(page),
        blocchi=[dict(tipo=t, posizione=p, lunghezza=len(s), inizio=s[:250].strip(), fine=s[-100:].strip())
                 for t, p, s in cand[:6]]))


@app.route('/api/debug4')
def debug4():
    """Cerca nei file JS come viene riempita tablematch1 e quali percorsi/file vengono richiamati."""
    from urllib.parse import urljoin
    base = URLS['live']
    pats = {'tablematch1': r'tablematch1', 'load': r'\.load\(', 'getScript': r'getScript', 'createElement': r'createElement\(.{0,3}script',
            'send': r'\.send\(', 'importScripts': r'importScripts|new Worker'}
    path = re.compile(r'["\']([\w./?=&:-]*(?:\.(?:php|js|json|txt|xml|csv|html|asp|aspx|ashx|gz|bin)|/[\w-]+/)[\w./?=&-]{0,40})["\']')
    out = {}
    try:
        page = requests.get(base, headers=HDR, timeout=20).text
        files = [s for s in re.findall(r'<script[^>]+src=["\']([^"\']+)', page) if s.startswith('/') and 'cookie' not in s.lower()]
        for f in files:
            js = requests.get(urljoin(base, f), headers=HDR, timeout=20).text
            res = {}
            for name, p in pats.items():
                hits, end = [], 0
                for m in re.finditer(p, js):
                    if m.start() < end:
                        continue
                    a, end = max(m.start() - 200, 0), m.end() + 200
                    hits.append(js[a:end])
                    if len(hits) >= (5 if name == 'tablematch1' else 2):
                        break
                if hits:
                    res[name] = hits
            res['percorsi'] = sorted(set(path.findall(js)))[:40]
            out[f] = res
    except Exception as e:
        out['errore'] = str(e)[:150]
    return jsonify(out)


@app.route('/api/debug5')
def debug5():
    """Mostra come lo script del sito costruisce l'indirizzo del file dati /tables/v4/..."""
    from urllib.parse import urljoin
    base = URLS['live']
    names = r'function\s+bb\b|\bbb\s*=|\bgS\s*=|\bbook\s*=|\bsdm\s*=|\bcvp\s*=|\bcvpc\s*=|function\s+get_date_offset|function\s+get_sel_date|\bundermaintenance\s*='
    out = {}
    try:
        page = requests.get(base, headers=HDR, timeout=20).text
        js_files = [s for s in re.findall(r'<script[^>]+src=["\']([^"\']+)', page) if s.startswith('/') and 'cookie' not in s.lower()]
        out['script_inline'] = [t.strip()[:1200] for t in re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', page, re.S) if t.strip()][:6]
        out['input_nascosti'] = re.findall(r'<input[^>]*type=["\']hidden["\'][^>]*>', page)[:30]
        for f in js_files:
            js = requests.get(urljoin(base, f), headers=HDR, timeout=20).text
            res = {}
            i = js.find('var currUrl')
            if i >= 0:
                res['prima_di_currUrl'] = js[max(i - 1500, 0):i + 150]
            hits, end = [], 0
            for m in re.finditer(names, js):
                if m.start() < end:
                    continue
                a, end = max(m.start() - 100, 0), m.end() + 220
                hits.append(js[a:end])
                if len(hits) >= 14:
                    break
            if hits:
                res['definizioni'] = hits
            if res:
                out[f] = res
    except Exception as e:
        out['errore'] = str(e)[:150]
    return jsonify(out)
