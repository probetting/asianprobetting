import json
from http.server import BaseHTTPRequestHandler

import requests
from bs4 import BeautifulSoup

try:
    from _parse import parse_asian
except ImportError:
    from api._parse import parse_asian

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
        for m in parse_asian(soup):
            m['kind'] = kind
            matches.append(m)
    return {'matches': matches, 'errors': errors}


def fetch_all():
    pages, errors = {}, {}
    for kind, url in URLS.items():
        try:
            r = requests.get(url, headers=HDR, timeout=20)
            r.encoding = r.encoding or 'utf-8'
            pages[kind] = r.text
            if r.status_code != 200:
                errors[kind] = f'HTTP {r.status_code}'
        except Exception as e:
            errors[kind] = str(e)[:120]
    d = build(pages)
    d['errors'] = {**errors, **d['errors']}
    return d


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(fetch_all(), ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)
