// Da una pagina qualsiasi di asianbetsoccer: carica LIVE, NEXT e PAST (una dopo l'altra, in finestre
// nascoste dello stesso sito), legge tutte le pagine dell'elenco e apre la webapp con i match.
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const box = document.createElement('div');
  box.style.cssText = 'position:fixed;left:12px;right:12px;bottom:16px;z-index:99999;padding:14px;border-radius:12px;font:700 16px system-ui;background:rgb(14,17,22);color:rgb(182,242,74);text-align:center;opacity:.95';
  document.body.appendChild(box);
  const sets = { live: 'livegame', next: 'tablenext', past: 'tablelast' };
  const trova = (chiavi, defs) => {
    const a = [...document.querySelectorAll('a[href]')].find(x => chiavi.some(c => x.getAttribute('href').toLowerCase().indexOf(c) >= 0));
    const r = [];
    const add = h => { try { const u = new URL(h, location.href).href; if (r.indexOf(u) < 0) r.push(u); } catch (e) {} };
    if (a) add(a.getAttribute('href'));
    defs.forEach(add);
    return r;
  };
  const url = { live: trova(['livescore'], ['/livescore.html']), next: trova(['nextgame'], ['/nextgame.html']), past: trova(['lastgame', 'pastgame'], ['/lastgame.html', '/pastgame.html', '/lastgames.html', '/pastgames.html']) };
  const tx = e => e.textContent.replace(/\s+/g, ' ').trim();
  const quando = e => [...e.childNodes].map(n => n.textContent.replace(/\s+/g, ' ').trim()).filter(Boolean).join(' ');
  const cells = r => [...r.children].filter(c => c.tagName === 'TD');
  const spans = e => [...e.querySelectorAll('span')].map(s => s.textContent.trim());
  const team = td => {
    const name = [...td.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('').replace(/\s+/g, ' ').trim();
    const cnt = k => [...td.querySelectorAll('span[class*=' + k + ']')].reduce((a, s) => a + (parseInt(s.textContent, 10) || 0), 0);
    return [name, cnt('yellow'), cnt('red')];
  };
  const leggi = async (kind, d) => {
    const out = [], seen = new Set();
    const t1 = d.getElementById('tablematch1'), t2 = d.getElementById('tablematch2');
    const parse = () => {
      const r1 = [...t1.querySelectorAll('tr')], r2 = [...t2.querySelectorAll('tr')];
      let league = '';
      r1.forEach((r, i) => {
        const t = cells(r);
        if (t.length === 1 && tx(t[0])) { league = tx(t[0]); return; }
        if (t.length < 9 || tx(t[0]) !== 'H' || i + 1 >= r1.length) return;
        const a = cells(r1[i + 1]);
        const [hn, hy, hr] = team(t[1]), [an, ay, ar] = team(a[1]);
        const m = { kind, league, home: hn, away: an, hy, hr, ay, ar, when: quando(t[2]), hg: tx(t[3]), ag: tx(a[2]), ht: tx(t[5]), x_cu: spans(t[7]), x_op: spans(t[8]), sh: null, sa: null };
        const h = r2[i + 2] ? cells(r2[i + 2]).map(tx) : [], w = r2[i + 3] ? cells(r2[i + 3]).map(tx) : [];
        if (h.length > 5 && h[0] === 'H' && w.length > 5 && w[0] === 'A') {
          m.sh = { cu: h[1], op: h[2], qcu: h[4], qop: h[5] };
          m.sa = { cu: w[1], op: w[2], qcu: w[4], qop: w[5] };
        }
        const k = league + '|' + hn + '|' + an;
        if (!seen.has(k)) { seen.add(k); out.push(m); }
      });
    };
    const info = () => { const e = d.getElementById('count_match'); return e ? e.textContent : ''; };
    const pag = () => d.getElementById('pagination');
    const attendi = async prima => {
      for (let i = 0; i < 100; i++) { await sleep(100); if (info() !== prima) break; }
      await sleep(500);
      return info() !== prima;
    };
    const primo = pag() && pag().querySelector('li[value="1"]');
    if (primo && !primo.classList.contains('active')) { const b = info(); primo.click(); await attendi(b); }
    for (let g = 0; g < 80; g++) {
      parse();
      box.textContent = kind.toUpperCase() + ': ' + out.length + ' match...';
      const n = (info().match(/\d+/g) || []).map(Number);
      const nx = pag() && pag().querySelector('li.next');
      if (!nx || n.length < 3 || n[1] >= n[2]) break;
      const b = info(); nx.click();
      if (!(await attendi(b))) break;
    }
    return out;
  };
  const provaUrl = async (kind, indirizzo) => {
    const f = document.createElement('iframe');
    f.style.cssText = 'position:fixed;left:0;top:0;width:1100px;height:800px;opacity:0;pointer-events:none;border:0';
    document.body.appendChild(f);
    f.src = indirizzo;
    await new Promise(r => { f.onload = r; setTimeout(r, 25000); });
    let d, w;
    try { d = f.contentDocument; w = f.contentWindow; d.body.tagName; } catch (e) { f.remove(); return null; }
    if (!d || !d.getElementById('tablematch1') || !d.getElementById('tablematch2')) { f.remove(); return null; }
    for (let i = 0; i < 150; i++) {
      await sleep(200);
      const n = d.getElementById('tablematch1').querySelectorAll('tr').length;
      const c = (d.getElementById('count_match') || {}).textContent || '';
      if (n > 0 || (i > 25 && /\d/.test(c))) break;
    }
    await sleep(500);
    if (String(w.cvp || '').indexOf(sets[kind]) !== 0) { f.remove(); return null; }
    const r = await leggi(kind, d);
    f.remove();
    return r;
  };
  const carica = async kind => {
    for (const u of url[kind]) { const r = await provaUrl(kind, u); if (r) return r; }
    return null;
  };
  const res = {}, falliti = [];
  for (const k of ['live', 'next', 'past']) {
    box.textContent = 'Carico ' + k.toUpperCase() + '...';
    let r = null;
    try { r = await carica(k); } catch (e) { r = null; }
    if (r) res[k] = r; else { falliti.push(k.toUpperCase()); box.textContent = k.toUpperCase() + ' non caricabile, continuo...'; await sleep(1200); }
  }
  if (!Object.keys(res).length) { box.textContent = 'Nessuna pagina caricata: sei su asianbetsoccer?'; return; }
  box.textContent = 'Fatto' + (falliti.length ? ' (mancano: ' + falliti.join(', ') + ')' : '') + '. Apro la webapp...';
  await sleep(falliti.length ? 1500 : 200);
  let bytes = new TextEncoder().encode(JSON.stringify({ s: res })), tipo = 'j';
  if (window.CompressionStream) {
    const cs = new Blob([bytes]).stream().pipeThrough(new CompressionStream('gzip'));
    bytes = new Uint8Array(await new Response(cs).arrayBuffer());
    tipo = 'g';
  }
  let bin = '';
  for (let i = 0; i < bytes.length; i += 8192) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 8192));
  const b64 = btoa(bin).split('+').join('-').split('/').join('_').replace(/=+$/, '');
  location.href = 'https:\x2f\x2fasianprobetting.vercel.app\x2f\u0023asian=' + tipo + b64;
})();
