"""Budgeted adapters, resumable search plans and commit-pinned source inspection."""
import base64, datetime, json, re, subprocess, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from .. import core as c
from .store import Store
from . import ranking

MODES=['hidden-gems','capability-expansion','performance-extremes','unusual-engineering','composable-infrastructure','forgotten-engineering','adjacency']
TECHNIQUES=['symbols','dependencies','reverse-dependencies','forks','papers','issues','discussions','releases','contributors','alternatives']
SOURCE_EXT={'.swift','.c','.cc','.cpp','.h','.m','.mm','.rs','.zig','.s','.asm','.py','.go'}
MANIFESTS={'Package.swift','Package.resolved','Cargo.toml','CMakeLists.txt','package.json','pyproject.toml','go.mod'}
REPO_LINK=re.compile(r'https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)')

def config():
    cfg=c.readjson(c.ROOT/'config/intelligence.json')
    if not cfg:raise RuntimeError('INTELLIGENCE_CONFIG_MISSING')
    if set(cfg['weights'])!=set(ranking.DIMENSIONS) or sum(cfg['weights'].values())!=100 or any(type(x) not in (int,float) or x<0 for x in cfg['weights'].values()):raise ValueError('Invalid scoring weights')
    for key,maximum in [('max_requests',18),('max_seconds',75),('max_response_bytes',2000000),('max_total_bytes',12000000),('max_candidates',8),('deep_candidates',3),('max_graph_hops',3),('max_frontier',500),('max_search_pages',3)]:
        if type(cfg[key]) is not int or not 1<=cfg[key]<=maximum:raise ValueError('Invalid bound: '+key)
    if cfg['modes']!=MODES or not 0.25<=cfg['request_interval_seconds']<=2 or not 60<=cfg['cache_seconds']<=604800:raise ValueError('Invalid modes/cache/rate policy')
    return cfg

def safe_words(text,limit=8):return ' '.join(re.findall(r'[A-Za-z0-9_]+',text)[:limit])
def endpoint(kind,q,page=1,count=8):return 'search/'+kind+'?'+urllib.parse.urlencode({'q':q,'per_page':count,'page':page})
def links(text):return sorted({m.rstrip('.').removesuffix('.git').lower() for m in REPO_LINK.findall(text)})[:20]

class CachedClient:
    def __init__(self,store,cfg,base):
        self.store=store;self.cfg=cfg;self.base=base;self.calls=0;self.bytes=0;self.hits=0;self.started=time.monotonic();self.last=0
    def budget(self):
        if self.calls>=self.cfg['max_requests'] or time.monotonic()-self.started>=self.cfg['max_seconds'] or self.bytes>=self.cfg['max_total_bytes']:raise RuntimeError('DISCOVERY_BUDGET')
    def get(self,path):
        if not path.startswith(('repos/','search/','users/','graphql?')) or '..' in urllib.parse.unquote(path.split('?')[0]).split('/'):raise ValueError('Unsafe API path')
        cached=self.store.cached(path,self.cfg['cache_seconds'])
        if cached is not None:self.hits+=1;return cached
        self.budget();delay=self.cfg['request_interval_seconds']-(time.monotonic()-self.last)
        if delay>0:time.sleep(delay)
        self.budget();self.calls+=1;self.last=time.monotonic()
        request_id=self.store.request_start(path)
        try:body=self.base.get(path)
        except BaseException:
            self.store.request_end(request_id,'failed_or_interrupted');raise
        size=len(c.canonical(body).encode());self.bytes+=size
        if size>self.cfg['max_response_bytes'] or self.bytes>self.cfg['max_total_bytes']:raise RuntimeError('RESPONSE_TOO_LARGE')
        self.store.request_end(request_id,'complete',size)
        self.store.cache(path,body);return body
    def public(self,name):
        from ..discovery import repo_id
        r=self.get('repos/'+repo_id(name))
        if r.get('private') is not False or r.get('visibility','public')!='public':raise RuntimeError('PUBLIC_REPOSITORY_REQUIRED')
        return r
    def papers(self,query):
        # Public objective only. Fixed scholarly endpoint, no project/corpus text or credentials.
        key='arxiv:'+query;cached=self.store.cached(key,self.cfg['cache_seconds'])
        if cached is not None:self.hits+=1;return cached
        self.budget();self.calls+=1
        request_id=self.store.request_start(key)
        url='https://export.arxiv.org/api/query?'+urllib.parse.urlencode({'search_query':'all:'+safe_words(query,5),'max_results':3})
        request=urllib.request.Request(url,headers={'User-Agent':'Pubster-public-research/2'})
        with urllib.request.urlopen(request,timeout=min(8,max(1,self.cfg['max_seconds']-(time.monotonic()-self.started)))) as response:
            if urllib.parse.urlparse(response.url).hostname not in ['export.arxiv.org','arxiv.org']:raise RuntimeError('PAPER_REDIRECT_BLOCKED')
            raw=response.read(min(self.cfg['max_response_bytes'],self.cfg['max_total_bytes']-self.bytes)+1)
        self.bytes+=len(raw)
        if len(raw)>self.cfg['max_response_bytes'] or self.bytes>self.cfg['max_total_bytes']:raise RuntimeError('RESPONSE_TOO_LARGE')
        root=ET.fromstring(raw);ns={'a':'http://www.w3.org/2005/Atom'}
        rows=[{'title':e.findtext('a:title',default='',namespaces=ns).strip(),'url':e.findtext('a:id',default='',namespaces=ns),'implementations':links(ET.tostring(e,encoding='unicode'))} for e in root.findall('a:entry',ns)]
        self.store.request_end(request_id,'complete',len(raw))
        self.store.cache(key,rows);return rows

def intent(objective,cfg,rotation=0):
    matches=ranking.concepts(objective,cfg)
    if matches:
        entry=cfg['intent_concepts'][matches[0]]
        return entry['queries'][rotation%len(entry['queries'])],entry['symbols'][rotation%len(entry['symbols'])],matches[0]
    return safe_words(objective.replace('Swift ','')),safe_words(objective,2),'unclassified:'+objective.lower()

def plan(seed,objective,mode,cfg,rotation,store):
    functional,symbol,concept=intent(objective,cfg,rotation)
    suffix={'hidden-gems':'','capability-expansion':'library','performance-extremes':'benchmark','unusual-engineering':'algorithm','composable-infrastructure':'library','forgotten-engineering':'archived:true','adjacency':''}[mode]
    # Meaning-based, curated intent expansion; deliberately no claim of learned embeddings.
    queries=[safe_words(objective)+' is:public',functional+' '+suffix+' is:public']
    feedback=store.meta('query-feedback:'+concept)
    if feedback:queries[1]=safe_words(feedback['search_terms'])+' is:public'
    tasks=[{'kind':'search','query':q.strip(),'order':'asc' if mode=='hidden-gems' else 'desc','sort':'stars' if mode=='hidden-gems' else 'updated'} for q in queries]
    technique=TECHNIQUES[rotation%len(TECHNIQUES)]
    tasks.append({'kind':technique,'seed':seed,'query':functional,'symbol':symbol,'hop':0,'origin':seed})
    if mode=='adjacency':
        approved=c.readjson(c.ROOT/'config/rights-policy.json',{}).get('approved_repositories',[])
        for name in approved:store.seed(name)
        row=store.db.execute("SELECT * FROM frontier WHERE state='pending' AND hop<? ORDER BY hop,origin,repository LIMIT 1",(cfg['max_graph_hops'],)).fetchone()
        if row:tasks.append({'kind':'dependencies','seed':row['repository'],'origin':row['origin'],'hop':row['hop'],'query':functional,'symbol':symbol,'frontier':True})
    return tasks,concept

def add_repo(found,r,provenance,cap=32):
    if r.get('private') is not False or r.get('visibility','public')!='public':return
    name=r.get('full_name','').lower()
    from ..discovery import repo_id
    try:repo_id(name)
    except ValueError:return
    if name not in found and len(found)>=cap:return
    if name not in found:found[name]={'metadata':r,'observations':[]}
    if provenance not in found[name]['observations']:found[name]['observations'].append(provenance)

def inspect(client,r):
    name=r['full_name'];branch=r.get('default_branch','main')
    commit=client.get('repos/'+name+'/commits/'+urllib.parse.quote(branch,safe=''))
    revision=commit['sha']
    if not re.fullmatch(r'[a-f0-9]{40}',revision):raise RuntimeError('INVALID_COMMIT_SHA')
    cached=client.store.meta('inspection:'+name.lower()+':'+revision)
    if cached and not cached.get('partial'):return cached
    tree=client.get('repos/'+name+'/git/trees/'+revision+'?recursive=1')
    entries=[e for e in tree.get('tree',[]) if e.get('type')=='blob' and e.get('size',0)<=100000]
    def kind(path):
        tail=path.split('/')[-1];low=path.lower()
        if tail in MANIFESTS:return 'manifest'
        if tail.lower().startswith('readme'):return 'documentation'
        if tail.lower().startswith(('license','copying')):return 'license'
        if any(low.endswith(x) for x in SOURCE_EXT) and not any(x in low for x in ['test','bench','vendor/','third_party/']):return 'source'
        return 'other'
    selected=[]
    for category in ['source','manifest','documentation','license']:
        candidates=sorted((e for e in entries if kind(e['path'])==category),key=lambda e:(len(e['path'].split('/')),e['path']))
        if candidates:selected.append(candidates[0])
    result={'revision':revision,'commit_at':commit.get('commit',{}).get('committer',{}).get('date'),'files':[],
      'test_paths':[e['path'] for e in entries if re.search(r'(^|/)(tests?|specs?)(/|\.)',e['path'],re.I)][:12],
      'benchmark_paths':[e['path'] for e in entries if re.search(r'bench(mark)?',e['path'],re.I)][:12],
      'tree_truncated':bool(tree.get('truncated')),'symbols':[],'dependencies':[],'paper_links':[],'executed':False}
    for e in selected:
        try:
            blob=client.get('repos/'+name+'/git/blobs/'+e['sha'])
            if blob.get('encoding')!='base64':continue
            raw=base64.b64decode(blob['content'],validate=False)
            if len(raw)>100000:continue
            text=raw.decode('utf-8',errors='replace');category=kind(e['path'])
            symbols=[{'name':m.group(1),'line':text[:m.start()].count('\n')+1,'status':'Source-supported','scope':'Declaration observed; behavior unverified'} for m in re.finditer(r'\b(?:func|fn|class|struct|enum|protocol|def)\s+([A-Za-z_][A-Za-z0-9_]*)',text)][:12]
            f={'path':e['path'],'blob_sha':e['sha'],'sha256':c.digest(raw),'url':'https://github.com/'+name+'/blob/'+revision+'/'+urllib.parse.quote(e['path']),'kind':category,'read':True,'symbols':symbols,'bytes':len(raw)}
            result['files'].append(f)
            if category=='source':result['symbols'].extend(symbols)
            if category=='manifest':result['dependencies'].extend(links(text))
            if category=='documentation':result['paper_links']=re.findall(r'https?://(?:arxiv\.org/abs/|doi\.org/)[^\s)>]+',text)[:8]
        except (RuntimeError,subprocess.TimeoutExpired) as exc:
            result['partial']=True;result['failure']=str(exc) if isinstance(exc,RuntimeError) else 'TIMEOUT';break
    result['dependency_manifests']=[f for f in result['files'] if f['kind']=='manifest']
    result['dependency_resolution']='PINNED_MANIFEST_LINKS_ONLY'
    client.store.setmeta('inspection:'+name.lower()+':'+revision,result)
    return result

def execute(task,client,store,found,cfg):
    kind=task['kind'];now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    provenance={'technique':kind,'at':now};artifacts=[]
    if kind=='search':
        key='page:'+c.digest(task['query']);page=store.meta(key,1)
        path=endpoint('repositories',task['query'],page)+'&'+urllib.parse.urlencode({'sort':task['sort'],'order':task['order']})
        data=client.get(path)
        for r in data.get('items',[]):add_repo(found,r,{**provenance,'query':task['query'],'page':page,'api_path':path})
        store.setmeta(key,page+1 if len(data.get('items',[]))==8 and page<cfg['max_search_pages'] else 1)
        return artifacts
    seed=task['seed'];root=client.public(seed);origin=task.get('origin',seed);hop=task.get('hop',0)
    targets=[]
    if kind=='symbols':
        path=endpoint('code',task['symbol']+' '+safe_words(task['query'],2),count=4)
        for x in client.get(path).get('items',[]):
            repo=x.get('repository',{});targets.append((repo.get('full_name'),{'url':x.get('html_url'),'symbol':task['symbol']}))
    elif kind=='dependencies':
        data=inspect(client,root)
        targets=[(x,{'revision':data['revision'],'manifests':data['dependency_manifests']}) for x in data['dependencies']]
        artifacts.append({'repository':seed,'inspection':data})
    elif kind=='reverse-dependencies':
        path=endpoint('code','"https://github.com/'+seed+'"',count=4)
        targets=[(x.get('repository',{}).get('full_name'),{'url':x.get('html_url')}) for x in client.get(path).get('items',[])]
    elif kind=='forks':
        rows=client.get('repos/'+seed+'/forks?sort=newest&per_page=3')
        for r in rows:
            branch=urllib.parse.quote(r.get('default_branch','main'),safe='')
            comparison=client.get('repos/'+seed+'/compare/'+urllib.parse.quote(root.get('default_branch','main'),safe='')+'...'+urllib.parse.quote(r['owner']['login'],safe='')+':'+branch)
            if comparison.get('ahead_by',0)>0:
                targets.append((r['full_name'],{'ahead_by':comparison['ahead_by'],'url':comparison.get('html_url'),'status':'Independent commits present; significance requires source review'}))
    elif kind=='papers':
        papers=client.papers(task['query']);artifacts.extend(papers)
        for paper in papers:
            targets.extend((x,{'paper':paper['url'],'title':paper['title']}) for x in paper['implementations'])
        if not targets:
            data=client.get(endpoint('repositories',safe_words(task['query'],3)+' paper in:readme is:public',count=4))
            for r in data.get('items',[]):add_repo(found,r,{**provenance,'status':'Paper-related search hit; paper relationship unverified'})
    elif kind=='issues':
        data=client.get(endpoint('issues',safe_words(task['query'],3)+' is:public',count=4))
        for x in data.get('items',[]):targets.extend((n,{'url':x['html_url'],'status':'Community claim'}) for n in links(x.get('body') or ''))
    elif kind=='discussions':
        owner,name=seed.split('/')
        query='query { repository(owner:'+json.dumps(owner)+',name:'+json.dumps(name)+') { discussions(first:1,orderBy:{field:UPDATED_AT,direction:DESC}) { nodes { url body } } } }'
        data=client.get('graphql?'+urllib.parse.urlencode({'query':query}))
        for x in ((data.get('data') or {}).get('repository') or {}).get('discussions',{}).get('nodes',[]):targets.extend((n,{'url':x['url'],'status':'Community claim'}) for n in links(x.get('body') or ''))
    elif kind=='releases':
        for x in client.get('repos/'+seed+'/releases?per_page=3'):targets.extend((n,{'url':x['html_url'],'status':'Release-note claim'}) for n in links(x.get('body') or ''))
    elif kind=='contributors':
        people=client.get('repos/'+seed+'/contributors?per_page=1')
        if people:
            login=people[0]['login']
            if not re.fullmatch(r'[A-Za-z0-9-]+',login):raise ValueError('Invalid contributor')
            for r in client.get('users/'+login+'/repos?sort=updated&per_page=4'):add_repo(found,r,{**provenance,'via_repository':seed,'status':'Contributor adjacency; relevance unverified'})
    elif kind=='alternatives':
        for r in client.get(endpoint('repositories',safe_words(task['query'])+' is:public',count=4)).get('items',[]):add_repo(found,r,{**provenance,'comparison_to':seed})
    for name,evidence in targets[:3]:
        if not name:continue
        # Relationships never imply public visibility, rights, or trust.
        r=client.public(name);canonical=r['full_name']
        add_repo(found,r,{**provenance,'via_repository':seed,'evidence':evidence})
        store.edge(origin,seed,canonical,kind,hop+1,evidence,cfg['max_frontier'],cfg['max_graph_hops'])
    if task.get('frontier'):
        with store.db:store.db.execute("UPDATE frontier SET state='expanded' WHERE origin=? AND repository=?",(origin.lower(),seed.lower()))
    return artifacts

def run(seed,objective,focused=False,mode=None):
    with c.lock('intelligence-ledger'):
        return _run(seed,objective,focused,mode)

def _run(seed,objective,focused=False,mode=None):
    from ..discovery import Client,repo_id
    seed=repo_id(seed)
    if not 1<=len(objective)<=160:raise ValueError('Public objective must be 1..160 characters')
    cfg=config();store=Store();started=time.monotonic()
    try:
        store.register(cfg);store.migrate(c.ROOT/'research/discovery')
        rotation=store.meta('rotation',0);mode=mode or MODES[rotation%len(MODES)]
        if mode not in MODES:raise ValueError('Unknown discovery mode')
        client=CachedClient(store,cfg,Client())
        root=client.public(seed) # Must precede any external scholarly query.
        tasks,concept=plan(seed,objective,mode,cfg,rotation,store)
        identity=c.identity(seed.lower(),objective,mode,cfg['scoring_version'])
        scan=store.begin(identity,mode,tasks);mode=scan['mode'];tasks=json.loads(scan['plan'])
        found=json.loads(scan['found']);errors=json.loads(scan['errors']);artifacts=[]
        cursor=scan['cursor'];prior_stats=json.loads(scan['stats'])
        for index,task in enumerate(tasks[cursor:],cursor):
            try:artifacts.extend(execute(task,client,store,found,cfg))
            except Exception as exc:
                reason=str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__
                errors.append({'technique':task['kind'],'reason':reason[:80],'at':int(time.time())})
                if reason=='DISCOVERY_BUDGET':break
            cursor=index+1
            store.checkpoint(scan['id'],cursor,found,errors,prior_stats)
        # Compare within language/age/purpose, never use stars as a proxy for quality.
        peers=[]
        for row in found.values():
            row['metadata']['purpose_concept']=concept;peers.append(row['metadata'])
        approved={r.lower() for r in c.readjson(c.ROOT/'config/rights-policy.json',{}).get('approved_repositories',[])}
        # Cheap eligibility, independent of final value score. Prefer new capabilities for inspection.
        eligible=sorted(found.values(),key=lambda row:(row['metadata']['full_name'].lower() in approved,-len(ranking.tokens(objective+' '+intent(objective,cfg)[0]) & ranking.tokens((row['metadata'].get('description') or '')+' '+' '.join(row['metadata'].get('topics',[])))),row['metadata']['full_name'].lower()))[:cfg['max_candidates']]
        previously_seen={row[0] for row in store.db.execute('SELECT DISTINCT repository FROM snapshots')}
        candidates=[];duplicates=0;deep=0
        for row in eligible:
            r=row['metadata'];data={};item=None
            if deep<cfg['deep_candidates']:
                try:
                    metadata=client.public(r['full_name'])
                    commit=client.get('repos/'+metadata['full_name']+'/commits/'+urllib.parse.quote(metadata.get('default_branch','main'),safe=''))
                    cached=store.snapshot(metadata['full_name'],commit['sha'],cfg['scoring_version'])
                    if cached and cached.get('inspection',{}).get('files'):
                        data=cached['inspection'];duplicates+=1
                    else:
                        data=inspect(client,metadata);r=metadata
                        if data.get('partial'):errors.append({'technique':'inspection','reason':data.get('failure','PARTIAL')})
                    deep+=1
                except Exception as exc:
                    errors.append({'technique':'inspection','reason':str(exc)[:80] if isinstance(exc,RuntimeError) else type(exc).__name__})
            review=store.review_context(r['full_name'],data.get('revision')) if data.get('revision') else {}
            data['review_evidence']=review.get('assessment',{})
            if item is None:item=ranking.candidate(r,data,cfg,peers,objective,mode,r['full_name'].lower() in approved)
            item['reviewed_capability_findings']=review.get('capability_findings',[])
            if review.get('recommendation'):item['recommendation']=review['recommendation']
            item=dict(item);item['objective']=objective;item['observations']=row['observations'];item['mode']=mode
            if item.get('revision'):item['stage']=store.stage(item['canonical_identity'],item['revision'])
            item['discovery_relation']='known repository / capability overlap requires review' if item['canonical_identity'] in approved else 'new repository / capability novelty unverified'
            candidates.append(item);store.save(item)
        candidates.sort(key=lambda x:(-x['score'],x['canonical_identity']))
        stats={'candidate_count':len(candidates),'unique_relevant_discoveries':sum(bool(x.get('capabilities')) and x['canonical_identity'] not in previously_seen for x in candidates),
          'relevance_scope':'Preliminary source availability and query eligibility, not human-verified utility',
          'high_value':sum(x['score']>=cfg['high_value_threshold'] for x in candidates),'duplicates':sum(x['canonical_identity'] in previously_seen for x in candidates),'unchanged_inspections_reused':duplicates,
          'requests':prior_stats.get('requests',0)+client.calls,'bytes':prior_stats.get('bytes',0)+client.bytes,'cache_hits':client.hits,
          'seconds':round(prior_stats.get('seconds',0)+time.monotonic()-started,2),'errors':len(errors),'inspected':deep,'verification_outcomes':{'executed':0,'source_supported':sum(x['evidence_status']=='Source-supported' for x in candidates)}}
        store.checkpoint(scan['id'],cursor,found,errors,stats)
        complete=cursor>=len(tasks)
        if complete:store.finish(scan['id'],stats);store.setmeta('rotation',rotation+1)
        return {'schema_version':2,'observed_at':int(time.time()),'seed':seed,'objective':objective,'mode':mode,'state':'COMPLETE' if complete else 'PARTIAL',
          'scan_id':scan['id'],'cursor':cursor,'tasks':len(tasks),'candidates':candidates,'errors':errors,'github_requests':client.base.calls,'network_requests':client.calls,
          'ecosyste_ms':{'state':'not_used'},'artifacts':artifacts,'metrics':stats,'cumulative_metrics':store.metrics(),
          'scoring_version':cfg['scoring_version'],'search_plan':tasks,'limits':{k:cfg[k] for k in ['max_requests','max_seconds','max_total_bytes','max_graph_hops']},
          'limitations':['Semantic intent uses versioned concept expansion, not learned embeddings','Only bounded high-potential candidates receive pinned code inspection','Source-supported is not executed or benchmark-verified','No automatic approval or corpus insertion']}
    finally:store.close()

def report(result):
    lines=['# Capability intelligence: '+result.get('target_id',result['objective']),'',
      'Mode: '+result.get('mode','legacy')+' | scoring: '+result.get('scoring_version','legacy')+' | state: '+result.get('state','unknown'),
      'Discovery is not corpus approval. Source-supported observations do not prove performance.','']
    for item in result['candidates']:
        lines.extend(['## '+item['repository'],item['url'],
          f"Score: {item['score']}/100 | {item.get('evidence_status','Unreviewed')} | {item.get('recommendation','investigate')}",
          'Revision: '+str(item.get('revision') or 'not yet resolved; awaiting enrichment'),
          'Purpose (project claim): '+item.get('actual_purpose',{}).get('text',item.get('description') or 'Unknown'),
          'Opportunity (speculative): '+result['objective'],
          'Swift integration: '+item.get('swift_integration','Review required'),
          'Overlap: '+item.get('discovery_relation','Unknown'),
          'Power: '+item.get('power_assessment','Unverified'),
          'Underexposure: '+item.get('underexposure_assessment',{}).get('status','Unknown'),
          'Maintenance: '+item.get('maintenance_risk',{}).get('assessment','Unknown'),
          'License: '+item.get('license','UNKNOWN')+'; compatibility unreviewed. Security: not audited.',''])
        for f in item.get('source_files',[]):lines.append('- '+f['kind']+': '+f['url'])
        for finding in item.get('reviewed_capability_findings',[]):
            lines.append('- Reviewed '+finding['relationship']+': '+finding['rationale']+' — '+finding['source_url'])
        lines.append('Next: review the pinned mechanism, compare an alternative, then prototype only with an explicit test plan.\n')
    lines.extend(['## Scan observations',c.canonical(result.get('metrics',{})),'','## Failures',c.canonical(result.get('errors',[])),''])
    return '\n'.join(line.rstrip() for line in lines).rstrip()+'\n'
