import json, re, time, html, urllib.request, urllib.parse

PATH='data/artifacts/tv_index.json'
doc=json.load(open(PATH)); series=doc['series']

def get(url):
    for a in range(4):
        try:
            with urllib.request.urlopen(url,timeout=20) as r: return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code==429: time.sleep(2+a); continue
            return None
        except Exception: time.sleep(1); continue
    return None
def strip(s):
    return html.unescape(re.sub(r'<[^>]+>','',s or '')).strip()
def singlesearch(t):
    return get('https://api.tvmaze.com/singlesearch/shows?embed=cast&q='+urllib.parse.quote(t))

# ---- 1) backfill poster_url for every show that lacks one ----
backfilled=0; still_missing=[]
for r in series:
    if r.get('poster_url'): continue
    d=singlesearch(r['title']); time.sleep(0.15)
    img=((d or {}).get('image') or {}).get('original') if d else None
    if img: r['poster_url']=img; backfilled+=1
    else: still_missing.append(r['title'])
print(f"backfilled posters: {backfilled};  still without: {still_missing}")

# ---- 2) add the 3 genuinely-missing shows ----
def search_list(q): return get('https://api.tvmaze.com/search/shows?q='+urllib.parse.quote(q)) or []
def cast_of(d): return [c['person']['name'] for c in (d.get('_embedded') or {}).get('cast',[])[:5] if c.get('person',{}).get('name')]
def mk(_id,title,d):
    return {'id':_id,'title':title,'year':int(d['premiered'][:4]) if d.get('premiered') else None,
            'type':'tv','genres':d.get('genres') or [],'cast':cast_of(d),
            'overview':strip(d.get('summary'))[:600],'poster_url':((d.get('image') or {}).get('original')),'tmdb_id':None}

next_id=max(x['id'] for x in series)+1
have={re.sub(r'[^a-z0-9]','',x['title'].lower()) for x in series}
to_add=[]
# House M.D. -> the 2004 Hugh Laurie medical drama named exactly "House"
res=search_list('House M.D.') + search_list('House')
house=None
for e in res:
    sh=e['show']
    if sh.get('name','').lower()=='house' and (sh.get('premiered') or '').startswith('2004'):
        house=get(f"https://api.tvmaze.com/shows/{sh['id']}?embed=cast"); break
if house: to_add.append(('House M.D.',house))
# The Underground Railroad (2021)
d=singlesearch('The Underground Railroad')
if d and d.get('image'): to_add.append(('The Underground Railroad',d))
# Generation War (German: Unsere Mutter, unsere Vater)
d=singlesearch('Unsere Mütter unsere Väter') or singlesearch('Generation War')
if d and d.get('image'): to_add.append(('Generation War',d))

added=[]
for title,d in to_add:
    k=re.sub(r'[^a-z0-9]','',title.lower())
    if k in have: continue
    rec=mk(next_id,title,d)
    if not rec['poster_url']: continue
    series.append(rec); have.add(k); next_id+=1; added.append(f"{title} ({rec['year']})")
print("added missing:", added)

doc['meta']['n_series']=len(series)
doc['meta']['all_have_poster']=all(x.get('poster_url') for x in series)
json.dump(doc,open(PATH,'w'),ensure_ascii=False,indent=1)
print(f"TOTAL series: {len(series)};  ALL have poster: {all(x.get('poster_url') for x in series)}")
