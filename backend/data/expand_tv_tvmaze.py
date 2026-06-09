import json, re, time, html, urllib.request, urllib.parse, sys

PATH = 'data/artifacts/tv_index.json'
doc = json.load(open(PATH))
series = doc['series']

def norm(t, spaces=True):
    t = t.lower()
    t = re.sub(r'\(.*?\)', '', t)
    t = re.sub(r'[^a-z0-9 ]', ' ' if spaces else '', t)
    w = [x for x in t.split() if x]
    if w and w[0] in ('the','a','an'): w = w[1:]
    if w and w[-1] in ('the','a','an'): w = w[:-1]
    s = ' '.join(w)
    return s if spaces else s.replace(' ','')

existing = {norm(x['title'], False) for x in series}
req = [s.strip() for s in open('/tmp/tvlist.txt').read().split(',') if s.strip()]
# unique, and only ones NOT already present
seen=set(); missing=[]
for r in req:
    k = norm(r, False)
    if k in seen or k in existing: continue
    seen.add(k); missing.append(r)

print(f"existing: {len(series)}  missing to add: {len(missing)}", flush=True)

def fetch_tvmaze(title):
    url = 'https://api.tvmaze.com/singlesearch/shows?embed=cast&q=' + urllib.parse.quote(title)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            if e.code == 429: time.sleep(2 + attempt); continue
            return None
        except Exception:
            time.sleep(1); continue
    return None

def strip_html(s):
    if not s: return ''
    s = re.sub(r'<[^>]+>', '', s)
    return html.unescape(s).strip()

next_id = max(x['id'] for x in series) + 1
added, skipped = [], []
for title in missing:
    d = fetch_tvmaze(title)
    time.sleep(0.18)  # be polite to TVmaze
    if not d:
        skipped.append((title, 'not found')); continue
    name = d.get('name') or title
    img = (d.get('image') or {}).get('original') or (d.get('image') or {}).get('medium')
    if not img:
        skipped.append((title, 'no poster')); continue
    # correctness guard: returned show must match the requested title
    if norm(name, False) != norm(title, False) and norm(title, False) not in norm(name, False) and norm(name, False) not in norm(title, False):
        skipped.append((title, f'mismatch->{name}')); continue
    cast = [c['person']['name'] for c in (d.get('_embedded') or {}).get('cast', [])[:5] if c.get('person',{}).get('name')]
    rec = {
        'id': next_id,
        'title': name,
        'year': int(d['premiered'][:4]) if d.get('premiered') else None,
        'type': 'tv',
        'genres': d.get('genres') or [],
        'cast': cast,
        'overview': strip_html(d.get('summary'))[:600],
        'poster_url': img,
        'tmdb_id': None,
    }
    series.append(rec); next_id += 1
    added.append(name)

doc['meta']['tvmaze_added'] = len(added)
doc['meta']['n_series'] = len(series)
json.dump(doc, open(PATH,'w'), ensure_ascii=False, indent=1)
print(f"ADDED {len(added)} shows. New total: {len(series)}", flush=True)
print("SKIPPED:", len(skipped))
for t,why in skipped: print(f"  - {t}: {why}")
