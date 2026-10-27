"""Bounded public metadata discovery. Never executes or approves candidate code."""
import json, re, subprocess, time, urllib.parse, urllib.request
from . import core as c

CACHE=c.ROOT/'.quality/discovery'
REPORT=c.ROOT/'research/discovery/latest.json'

def repo_id(value):
    value=value.removeprefix('https://github.com/').rstrip('/')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9_.-]{1,100}',value):
        raise ValueError('Expected owner/repository')
    return value

class Client:
    def __init__(self): self.calls=0; self.deadline=time.monotonic()+75
    def get(self,path):
        if self.calls>=18 or time.monotonic()>self.deadline: raise RuntimeError('DISCOVERY_BUDGET')
        self.calls+=1
        # Fixed GitHub host, GET only; auth stays inside gh.
        p=subprocess.run(['gh','api','--hostname','github.com','--method','GET',path],capture_output=True,timeout=min(12,max(1,self.deadline-time.monotonic())))
        if p.returncode: raise RuntimeError('GITHUB_UNAVAILABLE_OR_RATE_LIMITED')
        if len(p.stdout)>2_000_000: raise RuntimeError('RESPONSE_TOO_LARGE')
        return json.loads(p.stdout)
    def public(self,name):
        r=self.get('repos/'+repo_id(name))
        if r.get('private') is not False or r.get('visibility','public')!='public': raise RuntimeError('PUBLIC_REPOSITORY_REQUIRED')
        return r

def summary(r,objective):
    terms=set(re.findall(r'[a-z0-9]+',objective.lower()))
    text=' '.join([r.get('description') or '',r['full_name'],*r.get('topics',[])])
    matched=sorted(terms & set(re.findall(r'[a-z0-9]+',text.lower())))
    license=(r.get('license') or {}).get('spdx_id','UNKNOWN')
    score=len(matched)*10 + (3 if license not in ['UNKNOWN','NOASSERTION'] else 0) - (30 if r.get('archived') else 0)
    return dict(repository=r['full_name'],url=r['html_url'],description=r.get('description'),language=r.get('language'),license=license,archived=r.get('archived'),pushed_at=r.get('pushed_at'),topics=r.get('topics',[]),stars=r.get('stargazers_count'),score=score,matched_terms=matched,ranking='lexical-topic evidence, not semantic embeddings',rights='UNREVIEWED',security='NOT_AUDITED',compatibility='UNVERIFIED')

def implementations(client,name,term):
    name=repo_id(name)
    # Strip search operators so callers cannot expand the fixed public repo scope.
    words=re.findall(r'[A-Za-z0-9_]+',term)[:5]
    if not words: return []
    data=client.get('search/code?'+urllib.parse.urlencode({'q':' '.join(words)+' repo:'+name,'per_page':3}))
    return [dict(path=x['path'],url=x['html_url'],sha=x['sha']) for x in data.get('items',[]) if x.get('repository',{}).get('full_name','').lower()==name.lower()]

def inspect(client,r):
    name=repo_id(r['full_name']); branch=r.get('default_branch','main')
    commit=client.get('repos/'+name+'/commits/'+urllib.parse.quote(branch,safe=''))['sha']
    entries=client.get('repos/'+name+'/contents?ref='+commit)
    manifests={'Package.swift','Package.resolved','package.json','pyproject.toml','requirements.txt','Cargo.toml','go.mod'}
    return dict(revision=commit,dependency_manifests=[dict(path=e['path'],url='https://github.com/'+name+'/blob/'+commit+'/'+urllib.parse.quote(e['path']),sha=e['sha']) for e in entries if e['name'] in manifests],dependency_resolution='MANIFEST_REFERENCES_ONLY')

def discover(seed,objective):
    seed=repo_id(seed)
    if not 1<=len(objective)<=160: raise ValueError('Objective must be 1..160 characters and public')
    client=Client(); root=client.public(seed)
    terms=re.findall(r'[A-Za-z0-9_]+',objective)[:5]
    queries=[' '.join(terms)+' is:public archived:false']
    topics=root.get('topics',[])
    if topics: queries.append('topic:'+topics[0]+' is:public archived:false')
    found={seed:root}; errors=[]
    for q in queries:
        try:
            for r in client.get('search/repositories?'+urllib.parse.urlencode({'q':q,'per_page':8})).get('items',[]):
                if r.get('private') is False: found[r['full_name']]=r
        except (RuntimeError,subprocess.TimeoutExpired): errors.append('repository_search_unavailable')
    ranked=sorted((summary(r,objective) for r in found.values()),key=lambda r:(-r['score'],r['repository']))[:8]
    for item in ranked[:3]:
        try:
            item.update(inspect(client,found[item['repository']]))
            item['implementations']=implementations(client,item['repository'],terms[0] if terms else 'public')
        except (RuntimeError,subprocess.TimeoutExpired): item['inspection']='PARTIAL_OR_UNAVAILABLE'
    # Optional external metadata lookup: ONLY the already-confirmed public seed.
    eco='https://repos.ecosyste.ms/api/v1/hosts/GitHub/repositories/'+urllib.parse.quote(seed,safe='')
    try:
        with urllib.request.urlopen(urllib.request.Request(eco,headers={'User-Agent':'Pubster-public-discovery/1'}),timeout=5) as response:
            body=response.read(1_000_001)
            if len(body)>1_000_000: raise ValueError('large response')
            data=json.loads(body)
            ecosystem={'state':'available','url':eco,'manifests_count':data.get('manifests_count'),'dependencies_count':data.get('dependencies_count')}
    except Exception as e: ecosystem={'state':'unavailable','url':eco,'reason':type(e).__name__,'http_status':getattr(e,'code',None)}
    return dict(schema_version=1,observed_at=int(time.time()),seed=seed,objective=objective,candidates=ranked,errors=errors,github_requests=client.calls,ecosyste_ms=ecosystem,limitations=['No transitive dependency resolution or security audit','No learned semantic embeddings or shared-star graph','Candidates are not approved corpus sources'],companions={'starboard':'https://starboard.codevetter.com/','simrepo':'https://github.com/Mubelotix/SimRepo','sourcegraph':'https://sourcegraph.com/search','grep_app':'https://grep.app/','oss_insight':'https://ossinsight.io/'})

def tick(force=False):
    cfg=c.readjson(c.ROOT/'config/discovery.json')
    if not cfg or not cfg.get('enabled'): return {'state':'DISABLED'}
    targets=cfg.get('targets',[cfg])
    if not 1<=len(targets)<=8: raise ValueError('Expected 1..8 discovery targets')
    seen=set()
    for target in targets:
        key=target.get('id','default')
        if not re.fullmatch(r'[a-z0-9-]{1,40}',key) or key in seen: raise ValueError('Invalid or duplicate target id')
        seen.add(key)
    with c.lock('discovery'):
        due=[]
        for target in targets:
            path=REPORT.parent/(target.get('id','default')+'.json')
            prior=c.readjson(path)
            # Preserve the original report when upgrading from a single target.
            if prior is None:
                legacy=c.readjson(REPORT)
                if legacy and legacy.get('seed')==target['seed'] and legacy.get('objective')==target['public_objective']:
                    prior=legacy
                    c.writejson(path,prior)
            matches=prior and prior.get('seed')==target['seed'] and prior.get('objective')==target['public_objective']
            if force or not matches or time.time()-prior['observed_at']>=max(86400,cfg.get('refresh_seconds',86400)):
                due.append((prior['observed_at'] if matches else 0,target,path))
        if not due: return {'state':'CACHED','targets':len(targets)}
        # One oldest/missing target per tick preserves the original network budget.
        _,target,path=min(due,key=lambda row:row[0])
        result=discover(target['seed'],target['public_objective'])
        result['target_id']=target.get('id','default')
        c.writejson(CACHE/path.name,result)
        c.writejson(path,result)
        c.writejson(REPORT,result)
        lines=['# Adjacent repository candidates: '+result['target_id'],'','Discovery only: license, security and compatibility require review.','']
        for x in result['candidates']:
            lines += [f"- [{x['repository']}]({x['url']}): score {x['score']}; license {x['license']}; last push {x['pushed_at']}"]
        c.write(path.with_suffix('.md'),'\n'.join(lines)+'\n')
        c.write(REPORT.with_suffix('.md'),'\n'.join(lines)+'\n')
        return {'state':'COMPLETE','target':result['target_id'],'candidates':len(result['candidates']),'github_requests':result['github_requests'],'ecosyste_ms':result['ecosyste_ms']['state']}
