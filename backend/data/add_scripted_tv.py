import json, re, time, html, urllib.request, urllib.parse

PATH='data/artifacts/tv_index.json'
doc=json.load(open(PATH)); series=doc['series']

def norm(t):
    t=t.lower(); t=re.sub(r'\(.*?\)','',t); t=re.sub(r'[^a-z0-9]','',t)
    for a in ('the','a','an'):
        if t.startswith(a): t=t[len(a):]
    return t

existing={norm(x['title']) for x in series}
req=[r.strip() for r in open('/tmp/biglist_tv.txt').read().split(',') if r.strip()]
seen=set(); missing=[r for r in req if not (norm(r) in seen or seen.add(norm(r))) and norm(r) not in existing]
print(f"missing to consider: {len(missing)}", flush=True)

def get(url):
    for a in range(4):
        try:
            with urllib.request.urlopen(url,timeout=20) as r: return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code==429: time.sleep(2+a); continue
            return None
        except Exception: time.sleep(1); continue
    return None
def single(t): return get('https://api.tvmaze.com/singlesearch/shows?embed=cast&q='+urllib.parse.quote(t))
def strip(s): return html.unescape(re.sub(r'<[^>]+>','',s or '')).strip()

KEEP_TYPES={'scripted','animation'}
next_id=max(x['id'] for x in series)+1
added=[]; skip_type={}; skip_other=[]
for title in missing:
    d=single(title); time.sleep(0.15)
    if not d: skip_other.append((title,'not found')); continue
    name=d.get('name') or title
    # correctness guard
    if norm(name)!=norm(title) and norm(title) not in norm(name) and norm(name) not in norm(title):
        skip_other.append((title,f'mismatch->{name}')); continue
    typ=(d.get('type') or '').lower()
    img=((d.get('image') or {}).get('original'))
    if typ not in KEEP_TYPES:
        skip_type.setdefault(d.get('type') or '?',[]).append(title); continue
    if not img: skip_other.append((title,'no poster')); continue
    cast=[c['person']['name'] for c in (d.get('_embedded') or {}).get('cast',[])[:5] if c.get('person',{}).get('name')]
    series.append({'id':next_id,'title':name,'year':int(d['premiered'][:4]) if d.get('premiered') else None,
        'type':'tv','genres':d.get('genres') or [],'cast':cast,'overview':strip(d.get('summary'))[:600],
        'poster_url':img,'tmdb_id':None})
    next_id+=1; added.append(name)

doc['meta']['n_series']=len(series)
doc['meta']['all_have_poster']=all(x.get('poster_url') for x in series)
json.dump(doc,open(PATH,'w'),ensure_ascii=False,indent=1)
print(f"ADDED (scripted/animation): {len(added)}   TOTAL now: {len(series)}")
print("skipped by type:", {k:len(v) for k,v in skip_type.items()})
print("skipped other:", len(skip_other))
print("all have poster:", all(x.get('poster_url') for x in series))
