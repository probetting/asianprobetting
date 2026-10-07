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
        for m in parse_asian(soup):
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
