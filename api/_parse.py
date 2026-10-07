import re


def tx(c):
    return re.sub(r'\s+', ' ', c.get_text(' ', strip=True))


def spans(c):
    return [s.get_text(strip=True) for s in c.find_all('span')]


def team(td):
    """Nome pulito (solo testo diretto della cella) e cartellini (gialli, rossi)."""
    name = re.sub(r'\s+', ' ', ''.join(td.find_all(string=True, recursive=False))).strip()
    cnt = lambda key: sum(int(x.get_text(strip=True) or 0) for x in td.select(f'span[class*={key}]'))
    return name, cnt('yellow'), cnt('red')


def parse_asian(s):
    """s = pagina asianbetsoccer (BeautifulSoup). CU = attuale, OP = apertura."""
    r1 = s.find('table', id='tablematch1').find_all('tr')
    r2 = s.find('table', id='tablematch2').find_all('tr')
    out, league = [], ''
    for i, r in enumerate(r1):
        t = r.find_all('td', recursive=False)
        if len(t) == 1 and tx(t[0]):
            league = tx(t[0])
            continue
        if len(t) < 9 or tx(t[0]) != 'H' or i + 1 >= len(r1):
            continue
        a = r1[i + 1].find_all('td', recursive=False)
        (hn, hy, hr), (an, ay, ar) = team(t[1]), team(a[1])
        m = dict(league=league, home=hn, away=an, hy=hy, hr=hr, ay=ay, ar=ar, when=tx(t[2]),
                 hg=tx(t[3]), ag=tx(a[2]), ht=tx(t[5]),
                 x_cu=spans(t[7]), x_op=spans(t[8]), sh=None, sa=None)
        if i + 3 < len(r2):
            h = [tx(x) for x in r2[i + 2].find_all('td', recursive=False)]
            w = [tx(x) for x in r2[i + 3].find_all('td', recursive=False)]
            if len(h) > 5 and h[0] == 'H' and len(w) > 5 and w[0] == 'A':
                m['sh'] = dict(cu=h[1], op=h[2], qcu=h[4], qop=h[5])
                m['sa'] = dict(cu=w[1], op=w[2], qcu=w[4], qop=w[5])
        out.append(m)
    return out
