import hmac
import html
import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request

app = Flask(__name__)
VERSIONE = 'v5'

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


ROME = ZoneInfo('Europe/Rome')


def parse_iso(iso):
    try:
        return datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(ROME)
    except Exception:
        return None


def rome(iso):
    dt = parse_iso(iso)
    return dt.strftime('%d/%m %H:%M') if dt else iso


def spread_from_fv(fv):
    """Il campo fv delle righe di sinistra contiene 'spread_cu,spread_op_totale_cu,totale_op|...'."""
    m = re.match(r'\s*(-?[\d.]+),(-?[\d.]+)_', fv or '')
    return (m.group(1), m.group(2)) if m else None


def build(js, sig, kind, today=None):
    """Dal file dati del sito (chiamate getData*(...)) alla lista di match."""
    left, rights = [], []
    for m in re.finditer(r'\b(getData\w*)\(', js):
        name = m.group(1)
        if name not in sig or js[max(m.start() - 9, 0):m.start()] == 'function ':
            continue
        d = dict(zip(sig[name], parse_args(js, m.end() - 1)))
        if name == 'getData2':
            rights.append(d)
        elif 'homeStr' in d:
            left.append((name, d))
    # abbinamento riga sinistra/destra: per codice del match, poi per 'lc', infine per posizione
    keyed = {k: {d[k]: d for d in rights if d.get(k)} for k in ('curl', 'lc')}
    pair = []
    for _, d in left:
        pair.append(next((keyed[k][d[k]] for k in ('curl', 'lc') if d.get(k) in keyed[k]), None))
    if sum(1 for p in pair if p) < len(left) / 2 and len(rights) == len(left):
        pair = list(rights)
    scores, out = kind in ('live', 'past'), []
    today = today or datetime.now(ROME).date()
    for (name, d), r in zip(left, pair):
        if kind == 'next':  # prossimi: solo quelli di oggi, fino a mezzanotte (ora italiana)
            dt = parse_iso(d.get('datetimeStr', ''))
            if dt and dt.date() != today:
                continue
        h, a = d.get('gghomehtStr', ''), d.get('ggawayhtStr', '')
        sh = dict(cu=num(r['s1c']), op=num(r['s1o']), qcu=r['o1c'], qop=r['o1o']) if r and 's1c' in r and 'o1c' in r else None
        sa = dict(cu=num(r['s2c']), op=num(r['s2o']), qcu=r['o2c'], qop=r['o2o']) if r and 's2c' in r and 'o2c' in r else None
        fv = spread_from_fv(d.get('fv'))
        if not sh and fv:  # almeno la linea dello spread, senza quote
            sh = dict(cu=num(fv[0]), op=num(fv[1]), qcu='', qop='')
            sa = dict(cu=num(-float(fv[0])), op=num(-float(fv[1])), qcu='', qop='')
        out.append(dict(
            kind=kind, league=d.get('leagueStr', ''), home=d.get('homeStr', ''), away=d.get('awayStr', ''),
            hy=to_int(d.get('yellowcardhomeStr')), hr=to_int(d.get('redcardhomeStr')),
            ay=to_int(d.get('yellowcardawayStr')), ar=to_int(d.get('redcardawayStr')),
            when=(d.get('statusStr') or ('FT' if name == 'getDatalast1' else '')) if kind == 'live' else rome(d.get('datetimeStr', '')),
            hg=d.get('gghomeftStr', '') if scores else '', ag=d.get('ggawayftStr', '') if scores else '',
            ht=f'{h}-{a}' if scores and h.isdigit() and a.isdigit() else '',
            x_cu=[d.get('curr1Str', ''), d.get('currXStr', ''), d.get('curr2Str', '')],
            x_op=[d.get('open1Str', ''), d.get('openXStr', ''), d.get('open2Str', '')],
            sh=sh, sa=sa))
    return out


# Valori dei menu del sito (book e stats): usati solo se la pagina non si riesce a leggere
DEFAULT_BOOKS = [('4024db60a6b01ec72606b6de08a03d0a0f13c36c', '188Bet'), ('1743605751427885960fcda9d406c6562acf0947', 'Bet365'),
                 ('5114ca7854ec3b441d7b6eddd7365b7d6d98ec2c', 'Sbobet'), ('7b98090ef6e2d191e074fbdcebf44902ef27f939', 'Crown'),
                 ('26cc084a82bdf480f5c4ab66def0f1393f77c065', '12Bet'), ('8f6ec7b435c6e9cfbbf8541fe47601347b8408d0', '18Bet'),
                 ('f5425a19c52dafbf5944d66299181184989ebc8c', 'AvgOdds'), ('5d529f7175cc554d3a15435830dfbbf4ac829ff2', 'Bet365 Live')]
DEFAULT_STATS = [('Q', 'Basic'), ('A', 'Advance'), ('L', 'League')]


def fetch_all(book=None, stats=None, day=0, secs=('live', 'next'), past=None):
    problema = ''
    try:
        pr = requests.get(SITE + '/livescore.html', headers=HDR, timeout=20)
        page = pr.text
    except Exception as e:
        page, problema = '', str(e)[:80]
    soup = BeautifulSoup(page, 'lxml')
    opts = lambda sid: [(o.get('value'), o.get_text(strip=True)) for o in (soup.find(id=sid).find_all('option') if soup.find(id=sid) else [])]
    books, sts = opts('book_filter'), opts('stats_filter')
    if not books or not sts:
        if not problema:
            t = soup.find('title')
            problema = f'menu non trovati (HTTP {pr.status_code}, titolo "{(t.get_text(strip=True) if t else "")[:50]}")'
        books, sts = books or DEFAULT_BOOKS, sts or DEFAULT_STATS
    pick = lambda lst, want: next((v for v, t in lst if want and want.lower() in (v.lower(), t.lower())), lst[0][0])
    b, s = pick(books, book), pick(sts, stats)
    if not (past and re.fullmatch(r'\d{4}-\d{2}-\d{2}', past)):
        past = (datetime.now(ROME) - timedelta(days=1)).date().isoformat()
    sections = {'live': 'livegame', 'next': f'tablenext/day{day}', 'past': f'tablelast/{past}'}
    sig, ts = signatures(page), int(time.time()) * 1000
    matches, errors = [], {}
    for kind in secs:
        if kind not in sections:
            continue
        try:
            r = requests.get(f'{DATA}/{s}/{sections[kind]}/{b}.js?date={ts}', headers={**HDR, 'Referer': SITE + '/'}, timeout=25)
            if r.status_code != 200:
                errors[kind] = f'HTTP {r.status_code}'
                continue
            ms = build(r.text, sig, kind)
            if not ms and kind != 'past':
                names = dict(Counter(re.findall(r'\b(getData\w*)\(', r.text)))
                errors[kind] = f'nessun match letto ({len(r.text)} byte, chiamate {names})'
            matches += ms
        except Exception as e:
            errors[kind] = str(e)[:120]
    if problema and not matches:
        errors['pagina'] = problema
    return {'matches': matches, 'errors': errors, 'books': books}


@app.route('/api/refresh')
def refresh():
    secs = tuple(x for x in request.args.get('sec', 'live,next').split(',') if x)
    resp = jsonify(fetch_all(request.args.get('book'), request.args.get('stats'), to_int(request.args.get('day', 0)),
                             secs, request.args.get('past')))
    resp.headers['Cache-Control'] = 'no-store'
    return resp
@app.route('/api/versione')
def versione():
    return jsonify(versione=VERSIONE, prossimi='oggi (day0), fino a mezzanotte ora italiana')


def redis(*cmd):
    """Comando Redis via REST (Upstash collegato da Vercel: variabili KV_REST_API_URL e KV_REST_API_TOKEN)."""
    url = os.environ.get('KV_REST_API_URL') or os.environ.get('UPSTASH_REDIS_REST_URL')
    tok = os.environ.get('KV_REST_API_TOKEN') or os.environ.get('UPSTASH_REDIS_REST_TOKEN')
    if not url or not tok:
        raise RuntimeError('archivio non collegato')
    r = requests.post(url, headers={'Authorization': f'Bearer {tok}'}, json=list(cmd), timeout=10)
    r.raise_for_status()
    return r.json().get('result')


def key_ok():
    """Se su Vercel è impostata la variabile PPG_KEY, serve l'intestazione X-Key uguale."""
    k = os.environ.get('PPG_KEY')
    return (not k) or hmac.compare_digest(request.headers.get('X-Key', '').encode(), k.encode())


@app.route('/api/ppg', methods=['GET', 'POST'])
def ppg():
    """Lista PPG del giorno condivisa tra i dispositivi."""
    if not key_ok():
        return jsonify(errore='chiave errata'), 401
    try:
        if request.method == 'POST':
            d = request.get_json(force=True, silent=True) or {}
            ms = d.get('matches')
            if not isinstance(ms, list) or not ms or len(ms) > 5000:
                return jsonify(errore='lista non valida'), 400
            clean = [{k: str(m.get(k, ''))[:80] for k in ('home', 'away', 'ph', 'pa')} for m in ms if isinstance(m, dict)]
            body = {'date': str(d.get('date', ''))[:10], 'ts': int(d.get('ts') or 0), 'matches': clean}
            redis('SET', 'ppg', json.dumps(body, ensure_ascii=False), 'EX', 3 * 86400)
            return jsonify(ok=True, n=len(clean))
        raw = redis('GET', 'ppg')
        resp = jsonify(json.loads(raw) if raw else {})
    except Exception as e:
        resp = jsonify(errore=str(e)[:100])
        resp.status_code = 503
    resp.headers['Cache-Control'] = 'no-store'
    return resp
