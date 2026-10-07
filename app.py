import html
import re
import time
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request

app = Flask(__name__)

SITE = 'https://www.asianbetsoccer.com'
DATA = 'https://botbot3.space/tables/v4'
HDR = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
       'Accept-Language': 'en-US,en;q=0.9'}

_LEFT = ('lcl,pn,lc,fv,acx,curl,leagueStr,redcardhomeStr,yellowcardhomeStr,homeStr,datetimeStr,gghomeftStr,gghomehtStr,'
         'ggawayhtStr,curr1Str,currXStr,curr2Str,open1Str,openXStr,open2Str,redcardawayStr,yellowcardawayStr,awayStr,'
         'ggawayftStr,cornerhomeStr,cornerawayStr')
# Firme note delle funzioni del sito: servono solo se non si riesce a leggerle dal sito
SIG = {'getDatalast1': _LEFT.split(','), 'getDatalive1': (_LEFT + ',statusStr').split(','),
       'getData2': ('lcl,pn,lc,fv,curl,s1c,s1o,s1d,s2c,s2o,s2d,o1c,o1o,o1v,o1cd,o1od,o2c,o2o,o2v,o2cd,o2od,'
                    'tc,to,td,oc,oo,ov,ocd,ood,uc,uo,uv,ucd,uod').split(',')}


def unesc(s):
    s = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), s)
    s = re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m.group(1), 16)), s)
    return html.unescape(re.sub(r'\\(.)', r'\1', s))


def parse_args(js, i):
    """i = posizione della '(' di una chiamata; restituisce la lista degli argomenti (tutti come testo)."""
    args, n, j = [], len(js), i + 1
    while j < n:
        while j < n and js[j] in ' \t\r\n,':
            j += 1
        if j >= n or js[j] == ')':
            break
        if js[j] in '\'"':
            q, k, buf = js[j], j + 1, []
            while k < n and js[k] != q:
                if js[k] == '\\' and k + 1 < n:
                    buf.append(js[k:k + 2])
                    k += 2
                else:
                    buf.append(js[k])
                    k += 1
            args.append(unesc(''.join(buf)))
            j = k + 1
        else:
            k = j
            while k < n and js[k] not in ',)':
                k += 1
            args.append(js[j:k].strip())
            j = k
    return args


def signatures(page):
    """Nomi dei parametri delle funzioni getData* letti da tablefunc; altrimenti quelli noti."""
    sig = dict(SIG)
    m = re.search(r'src=["\'](/settings/tablefunc[^"\']+)', page)
    if m:
        try:
            tf = requests.get(SITE + m.group(1), headers=HDR, timeout=20).text
            for f in re.finditer(r'function\s+(getData\w*)\s*\(([^)]*)\)', tf):
                sig[f.group(1)] = [p.strip() for p in f.group(2).split(',')]
        except Exception:
            pass
    return sig


def num(x):
    try:
        return '%g' % float(x)
    except (TypeError, ValueError):
        return x or ''


def to_int(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return 0


def rome(iso):
    try:
        return datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(ZoneInfo('Europe/Rome')).strftime('%d/%m %H:%M')
    except Exception:
        return iso


def build(js, sig, kind):
    """Dal file dati del sito (chiamate getData*(...)) alla lista di match."""
    left, right = [], {}
    for m in re.finditer(r'\b(getData\w*)\(', js):
        name = m.group(1)
        if name not in sig or js[max(m.start() - 9, 0):m.start()] == 'function ':
            continue
        d = dict(zip(sig[name], parse_args(js, m.end() - 1)))
        if name == 'getData2':
            right[d.get('curl')] = d
        elif 'homeStr' in d:
            left.append((name, d))
    live, out = kind == 'live', []
    for name, d in left:
        r = right.get(d.get('curl'))
        h, a = d.get('gghomehtStr', ''), d.get('ggawayhtStr', '')
        out.append(dict(
            kind=kind, league=d.get('leagueStr', ''), home=d.get('homeStr', ''), away=d.get('awayStr', ''),
            hy=to_int(d.get('yellowcardhomeStr')), hr=to_int(d.get('redcardhomeStr')),
            ay=to_int(d.get('yellowcardawayStr')), ar=to_int(d.get('redcardawayStr')),
            when=(d.get('statusStr') or ('FT' if name == 'getDatalast1' else '')) if live else rome(d.get('datetimeStr', '')),
            hg=d.get('gghomeftStr', '') if live else '', ag=d.get('ggawayftStr', '') if live else '',
            ht=f'{h}-{a}' if live and h.isdigit() and a.isdigit() else '',
            x_cu=[d.get('curr1Str', ''), d.get('currXStr', ''), d.get('curr2Str', '')],
            x_op=[d.get('open1Str', ''), d.get('openXStr', ''), d.get('open2Str', '')],
            sh=dict(cu=num(r['s1c']), op=num(r['s1o']), qcu=r['o1c'], qop=r['o1o']) if r and 's1c' in r and 'o1c' in r else None,
            sa=dict(cu=num(r['s2c']), op=num(r['s2o']), qcu=r['o2c'], qop=r['o2o']) if r and 's2c' in r and 'o2c' in r else None))
    return out


def fetch_all(book=None, stats=None, day=0):
    try:
        page = requests.get(SITE + '/livescore.html', headers=HDR, timeout=20).text
    except Exception as e:
        return {'matches': [], 'errors': {'pagina': str(e)[:120]}}
    soup = BeautifulSoup(page, 'lxml')
    opts = lambda sid: [(o.get('value'), o.get_text(strip=True)) for o in (soup.find(id=sid).find_all('option') if soup.find(id=sid) else [])]
    books, sts = opts('book_filter'), opts('stats_filter')
    if not books or not sts:
        return {'matches': [], 'errors': {'pagina': 'menu book/stats non trovati'}}
    pick = lambda lst, want: next((v for v, t in lst if want and want.lower() in (v.lower(), t.lower())), lst[0][0])
    b, s = pick(books, book), pick(sts, stats)
    sig, ts = signatures(page), int(time.time()) * 1000
    matches, errors = [], {}
    for kind, section in (('live', 'livegame'), ('next', f'tablenext/day{day}')):
        try:
            r = requests.get(f'{DATA}/{s}/{section}/{b}.js?date={ts}', headers={**HDR, 'Referer': SITE + '/'}, timeout=25)
            if r.status_code != 200:
                errors[kind] = f'HTTP {r.status_code}'
                continue
            ms = build(r.text, sig, kind)
            if not ms:
                names = dict(Counter(re.findall(r'\b(getData\w*)\(', r.text)))
                errors[kind] = f'nessun match letto ({len(r.text)} byte, chiamate {names})'
            matches += ms
        except Exception as e:
            errors[kind] = str(e)[:120]
    return {'matches': matches, 'errors': errors, 'books': books}


@app.route('/api/refresh')
def refresh():
    resp = jsonify(fetch_all(request.args.get('book'), request.args.get('stats'), to_int(request.args.get('day'))))
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.route('/api/debug-ppg')
def debug_ppg():
    """Prova a leggere probettinghub dal server e mostra da dove prende i dati."""
    url = 'https://probettinghub.com/it/pro-finder'
    out = {}
    try:
        r = requests.get(url, headers=HDR, timeout=25)
        t = r.text
        out.update(status=r.status_code, bytes=len(t), titolo=(re.search(r'<title[^>]*>(.*?)</title>', t, re.S) or [None, ''])[1].strip()[:120],
                   server=r.headers.get('server'), cloudflare='cf-ray' in r.headers)
        out['indizi'] = {k: t.count(k) for k in ['__NEXT_DATA__', 'self.__next_f', 'application/json', '<table', 'ppg', 'PPG']}
        out['script_src'] = re.findall(r'<script[^>]+src=["\']([^"\']+)', t)[:12]
        out['url_api'] = sorted(set(re.findall(r'["\'](https?://[^"\'\s<>]*(?:api|supabase|graphql|firebase|rest)[^"\'\s<>]*|/api/[^"\'\s<>]*)', t)))[:15]
        m = re.search(r'ppg', t, re.I)
        out['intorno_ppg'] = t[max(m.start() - 200, 0):m.start() + 300] if m else None
    except Exception as e:
        out['errore'] = str(e)[:150]
    return jsonify(out)
