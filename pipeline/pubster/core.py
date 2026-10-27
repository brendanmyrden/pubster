"""Bounded local-first corpus pipeline. Upstream content is inert data."""
from __future__ import annotations
import base64, contextlib, datetime, fcntl, gzip, hashlib, json, os, re, shutil, sqlite3, subprocess, time, urllib.request, urllib.error
from pathlib import Path
from markdown_it import MarkdownIt
from jsonschema import validate as schema_validate
ROOT=Path(__file__).resolve().parents[2]
STATE=Path(os.environ.get('PUBSTER_STATE','/Volumes/SYYR/Pubster-state'))
VERSION='0.2.0'
def canonical(v): return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def digest(v): return hashlib.sha256(v if isinstance(v,bytes) else v.encode()).hexdigest()
def identity(*parts): return 'sha256:'+digest(canonical(parts))
def readjson(p,default=None): return json.loads(p.read_text()) if p.exists() else default
def write(p,v):
    p=Path(p); p.parent.mkdir(parents=True,exist_ok=True)
    data=v if isinstance(v,bytes) else v.encode()
    if p.exists() and p.read_bytes()==data: return
    temp=p.with_name(p.name+'.tmp'); temp.write_bytes(data); os.replace(temp,p)
def writejson(p,v): write(p,canonical(v)+'\n')
def rows(p): return [json.loads(x) for x in p.read_text().splitlines() if x]
def init():
    if str(STATE).startswith('/Volumes/SYYR/') and not os.path.ismount('/Volumes/SYYR'): raise RuntimeError('EXTERNAL_DRIVE_UNAVAILABLE')
    for x in ['state','raw','exports','logs','locks','backups','cache','evaluator']: (STATE/x).mkdir(parents=True,exist_ok=True)
    db=connect(); db.executescript((ROOT/'pipeline/schema.sql').read_text()); db.close()
    db=connect()
    for p in ['sources.seed.jsonl','sources.supplemental.jsonl']:
        for r in rows(ROOT/'config'/p): db.execute('INSERT OR IGNORE INTO sources VALUES (?,?)',(r['source_id'],canonical(r)))
    db.commit();db.close()
def connect():
    db=sqlite3.connect(STATE/'state/pubster.sqlite3',timeout=5); db.row_factory=sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON'); db.execute('PRAGMA journal_mode=WAL'); db.execute('PRAGMA synchronous=NORMAL');return db
@contextlib.contextmanager
def lock(name='writer'):
    initpath=STATE/'locks';initpath.mkdir(parents=True,exist_ok=True)
    with (initpath/(name+'.lock')).open('a') as f:
        try: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('SKIPPED_ALREADY_RUNNING')
        try: yield
        finally: fcntl.flock(f,fcntl.LOCK_UN)
class Fetcher:
    def __init__(self): self.bytes=0;self.requests=0;self.started=time.monotonic()
    def get(self,url):
        from urllib.parse import urlparse
        p=urlparse(url)
        if p.scheme!='https' or p.hostname not in ['api.github.com','raw.githubusercontent.com'] or p.username or p.port: raise ValueError('URL_BLOCKED')
        if self.requests>=100 or time.monotonic()-self.started>300: raise RuntimeError('FETCH_BUDGET')
        self.requests+=1
        cache=STATE/'cache'/digest(url); meta=readjson(cache.with_suffix('.json'),{})
        headers={'User-Agent':'Pubster/0.1 (+private research library)','Accept':'application/vnd.github+json'}
        if meta.get('etag') and cache.exists(): headers['If-None-Match']=meta['etag']
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args): raise ValueError('REDIRECT_REVIEW_REQUIRED')
        for attempt in range(3):
            try:
                with urllib.request.build_opener(NoRedirect).open(urllib.request.Request(url,headers=headers),timeout=20) as response:
                    chunks=[];size=0
                    while True:
                        chunk=response.read(65536)
                        if not chunk:break
                        size+=len(chunk);self.bytes+=len(chunk)
                        if size>2097152 or self.bytes>52428800:raise RuntimeError('FETCH_SIZE_LIMIT')
                        chunks.append(chunk)
                    data=b''.join(chunks);write(cache,data);writejson(cache.with_suffix('.json'),{'etag':response.headers.get('ETag')});return data
            except urllib.error.HTTPError as e:
                if e.code==304:return cache.read_bytes()
                if e.code not in [429,500,502,503,504] or attempt==2:raise RuntimeError('HTTP_'+str(e.code)) from None
                time.sleep(min(3,attempt+1))
        raise RuntimeError('FETCH_FAILED')
    def api(self,path):return json.loads(self.get('https://api.github.com/'+path))
def verify_license(body,spdx,expected_hash=None):
    if expected_hash and digest(body)!=expected_hash:raise RuntimeError('LICENSE_CHANGED_REVIEW_REQUIRED')
    valid=(spdx=='Apache-2.0' and b'Apache License' in body and b'Version 2.0' in body) or (spdx=='MIT' and b'Permission is hereby granted, free of charge' in body and b'THE SOFTWARE IS PROVIDED' in body)
    if not valid:raise RuntimeError('LICENSE_MISMATCH')

def approved_sources(): return readjson(ROOT/'config/rights-policy.json')['approved_repositories']
def ingest(force=False,max_sources=2):
    init(); f=Fetcher();db=connect();changed=0;counts={};attempted=0
    for repo in approved_sources():
        source=next(json.loads(r[0]) for r in db.execute('SELECT record_json FROM sources') if json.loads(r[0])['label']==repo)
        sid=source['source_id']; previous=db.execute('SELECT checked_at,commit_sha FROM source_revisions WHERE source_id=?',(sid,)).fetchone()
        if previous and not force and time.time()-previous['checked_at']<86400:counts[sid]='fresh';continue
        if attempted>=max_sources:counts[sid]='deferred_source_budget';continue
        attempted+=1
        review=readjson(ROOT/'config/rights-policy.json').get('repository_reviews',{}).get(repo,{})
        spdx=review.get('spdx','Apache-2.0');license_path=review.get('license_path','LICENSE.txt')
        info=f.api('repos/'+repo)
        if info['full_name']!=repo or info['archived'] or (info.get('license') or {}).get('spdx_id')!=spdx: raise RuntimeError('RIGHTS_REVIEW_REQUIRED')
        commit=f.api('repos/'+repo+'/commits/'+info['default_branch'])['sha']
        if review and commit!=review['commit']:
            counts[sid]='new_revision_requires_review';continue
        if previous and previous['commit_sha']==commit:
            db.execute('UPDATE source_revisions SET checked_at=? WHERE source_id=?',(int(time.time()),sid));db.commit();counts[sid]='unchanged';continue
        license_bytes=f.get(f'https://raw.githubusercontent.com/{repo}/{commit}/{license_path}')
        verify_license(license_bytes,spdx,review.get('license_sha256'))
        evidence=identity(repo,commit,license_path,digest(license_bytes))
        write(STATE/'raw'/digest(license_bytes),license_bytes)
        tree=f.api('repos/'+repo+'/git/trees/'+commit+'?recursive=1')
        if tree.get('truncated'):raise RuntimeError('TREE_TRUNCATED')
        paths=sorted(x['path'] for x in tree['tree'] if x['type']=='blob' and x['path'].endswith('.md') and (x['path']=='README.md' or x['path'].startswith(('Guides/','Documentation/'))))[:35]
        if review:
            # Review grants only these pinned document bytes, not the entire repository.
            if commit!=review['commit']: raise RuntimeError('NEW_REVISION_REVIEW_REQUIRED')
            paths=[review['readme_path']]
        source['rights']['spdx_expression']=spdx
        notices={}
        for x in tree['tree']:
            if x['type']=='blob' and '/' not in x['path'] and x['path'].upper().startswith(('NOTICE','LICENSE')):
                notices[x['path']]=f.get(f'https://raw.githubusercontent.com/{repo}/{commit}/{x["path"]}').decode()
        allchunks=[]
        for path in paths:
            raw=f.get(f'https://raw.githubusercontent.com/{repo}/{commit}/{path}');text=raw.decode('utf-8')
            if review and digest(raw)!=review['readme_sha256']:raise RuntimeError('DOCUMENT_REVIEW_MISMATCH')
            write(STATE/'raw'/digest(raw),raw)
            allchunks+=chunk_markdown(text,source,repo,commit,path,evidence)
        if not allchunks:raise RuntimeError('EMPTY_SOURCE')
        quality_gate(allchunks)
        source.update(canonical_url='https://github.com/'+repo,status='indexed',authority='official')
        source['verification'].update(default_branch=info['default_branch'],resolved_commit=commit,archived=False,license_evidence=[evidence])
        source['rights'].update(status='redistribute_approved',spdx_expression=spdx,can_fetch_full_text=True,can_redistribute=True)
        with db:
            old={r[0] for r in db.execute('SELECT chunk_id FROM chunks WHERE source_id=?',(sid,))}; new={r['chunk_id'] for r in allchunks}
            for cid in old-new:db.execute('INSERT OR IGNORE INTO tombstones VALUES (?,?)',(cid,commit))
            db.execute('DELETE FROM chunks WHERE source_id=?',(sid,))
            for c in allchunks:store_chunk(db,c)
            db.execute('INSERT OR REPLACE INTO sources VALUES (?,?)',(sid,canonical(source)))
            db.execute('INSERT OR REPLACE INTO source_revisions VALUES (?,?,?,?)',(sid,commit,int(time.time()),canonical(paths)))
            db.execute('INSERT OR REPLACE INTO license_evidence VALUES (?,?,?,?)',(evidence,sid,digest(license_bytes),canonical(notices)))
        counts[sid]=len(allchunks);changed+=1
    db.close();return {'changed_sources':changed,'sources':counts,'download_bytes':f.bytes,'requests':f.requests}
def chunk_markdown(text,source,repo,commit,path,evidence):
    lines=text.splitlines(keepends=True);tokens=MarkdownIt('commonmark').enable('table').parse(text)
    sections=[];start=0;title=path;heading=[]
    for i,t in enumerate(tokens):
        if t.type=='heading_open' and t.map:
            n=t.map[0]
            if n>start:sections.append((start,n,title,heading.copy()))
            title=tokens[i+1].content;level=int(t.tag[1:]);heading=heading[:level-1]+[title];start=n
    if start<len(lines):sections.append((start,len(lines),title,heading))
    out=[]
    for start,end,title,heading in sections:
        # Preserve whole parser blocks/code fences. Oversized sections stay excluded, never cut mid-code.
        body=''.join(lines[start:end]).strip()
        if len(body)<40 or len(body)>8000:continue
        did=identity(source['source_id'],path,'en');rid=identity(did,commit,digest(text));cid=identity(rid,[start+1,end],digest(body))
        c={'schema_version':'1.0','chunk_id':cid,'document_id':did,'revision_id':rid,'source_id':source['source_id'],'kind':'reference','title':title,'heading_path':heading,'body_markdown':body,'body_text':body,'language':'en','code_languages':sorted(set(re.findall(r'```(\w+)',body))),'domains':[source['domain']],'topics':[],'symbols':[],'platforms':[],'availability':{'swift_toolchain':None,'swift_language_mode':None,'xcode':None,'os_minimums':{},'evidence':[]},'origin':{'canonical_url':f'https://github.com/{repo}/blob/{commit}/{path}#L{start+1}-L{end}','repository':repo,'commit':commit,'path':path,'line_start':start+1,'line_end':end,'anchor':None,'raw_sha256':digest(text)},'rights':{'status':'redistribute_approved','license_ids':[source.get('rights',{}).get('spdx_expression','Apache-2.0')],'license_evidence_ids':[evidence],'attribution_ids':[evidence],'can_send_to_inference_provider':False},'verification':{'state':'source_verified','code_test_state':'not_run','evidence_ids':[evidence],'reviewed_at':None},'derived':False,'parent_chunk_ids':[],'extractor':{'name':'markdown-it-py','version':'4.0.0'}}
        out.append(c)
    return out
def store_chunk(db,c):
    db.execute('INSERT INTO chunks(chunk_id,document_id,revision_id,source_id,title,body_text,body_markdown,tags,record_json,status,redistribute,content_sha256) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(c['chunk_id'],c['document_id'],c['revision_id'],c['source_id'],c['title'],c['body_text'],c['body_markdown'],' '.join(c['domains']),canonical(c),'accepted',1,digest(c['body_markdown'])))
def validate_records(records,db):
    schema=readjson(ROOT/'packages/schemas/chunk.json');evidence={r[0] for r in db.execute('SELECT evidence_id FROM license_evidence')}
    for c in records:
        schema_validate(c,schema)
        assert c['rights']['status']=='redistribute_approved' and set(c['rights']['license_evidence_ids'])<=evidence,'RIGHTS_INVALID'
        assert not c['derived'] and c['verification']['code_test_state']=='not_run'
        origin=c['origin'];raw=(STATE/'raw'/origin['raw_sha256']).read_text()
        assert digest(raw)==origin['raw_sha256'],'RAW_HASH_INVALID'
        assert ''.join(raw.splitlines(keepends=True)[origin['line_start']-1:origin['line_end']]).strip()==c['body_markdown'],'PROVENANCE_INVALID'
        assert not re.search(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN .*PRIVATE KEY|/Users/)',c['body_markdown']),'SECRET_SCAN_FAILED'
    return len(records)
def search(q,limit=20,source=None,domain=None,weight=None):
    terms=re.findall(r'[\w]+',q[:256],re.UNICODE)[:12]
    if not terms:return []
    expr=' AND '.join('"'+t+'"' for t in terms)
    weight=weight or readjson(STATE/'state/retrieval.json',{'title_weight':2})['title_weight']
    db=connect();conditions=['chunks_fts MATCH ?'];params=[expr]
    if source:conditions.append('c.source_id=?');params.append(source)
    if domain:conditions.append('c.tags=?');params.append(domain)
    sql=f'SELECT c.record_json FROM chunks_fts JOIN chunks c ON c.rowid=chunks_fts.rowid WHERE {" AND ".join(conditions)} ORDER BY bm25(chunks_fts,{float(weight)},1,1),c.chunk_id LIMIT ?'
    result=[json.loads(r[0]) for r in db.execute(sql,params+[min(max(int(limit),1),50)])];db.close();return result
def quality_gate(records):
    """Separate environment, bounded subprocess, staged immutable input on SYYR."""
    data=''.join(canonical(r)+'\n' for r in sorted(records,key=lambda x:x['chunk_id']))
    staged=ROOT/'.quality/staged'/(digest(data)+'.jsonl')
    write(staged,data)
    try:
        result=subprocess.run([str(ROOT/'scripts/pubster-quality'),str(staged)],cwd=ROOT,
            text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180)
    except subprocess.TimeoutExpired:
        raise RuntimeError('QUALITY_TIMEOUT') from None
    if result.returncode:
        write(ROOT/'.quality/reports/last-failure.log',result.stdout[-4000:]+result.stderr[-4000:])
        raise RuntimeError('QUALITY_GATE_FAILED')
    return json.loads(result.stdout.splitlines()[-1])

def export():
    db=connect();records=[json.loads(r[0]) for r in db.execute('SELECT record_json FROM chunks ORDER BY chunk_id')]
    if not records:raise RuntimeError('NO_ACCEPTED_RECORDS')
    validate_records(records,db)
    quality_gate(records)
    sources=[json.loads(r[0]) for r in db.execute('SELECT record_json FROM sources ORDER BY source_id')]
    cid=identity(VERSION,[r['chunk_id'] for r in records],sources).split(':')[1];out=STATE/'exports'/cid
    out.mkdir(exist_ok=True)
    def jsonl(items):return ''.join(canonical(r)+'\n' for r in items)
    write(out/'chunks.jsonl.gz',gzip.compress(jsonl(records).encode(),mtime=0))
    write(out/'sources.jsonl',jsonl(sources))
    docs={r['document_id']:{'document_id':r['document_id'],'revision_id':r['revision_id'],'source_id':r['source_id'],'origin':r['origin']} for r in records}
    write(out/'documents.jsonl.gz',gzip.compress(jsonl([docs[k] for k in sorted(docs)]).encode(),mtime=0))
    for name in ['concepts','examples']:write(out/(name+'.jsonl.gz'),gzip.compress(b'',mtime=0))
    rights=[];notices=[];source_licenses={s['source_id']:s['rights'].get('spdx_expression','NOASSERTION') for s in sources}
    for e in db.execute('SELECT * FROM license_evidence ORDER BY evidence_id'):
        rights.append({'evidence_id':e['evidence_id'],'source_id':e['source_id'],'license_sha256':e['license_sha256'],'license':source_licenses[e['source_id']]})
        for name,body in json.loads(e['notices_json']).items():write(out/'rights/licenses'/e['source_id']/name,body)
        notices.append(e['source_id']+' — upstream repository content, '+source_licenses[e['source_id']]+'; originals preserved without modification. See source URL, commit and line spans per record.\n')
    write(out/'rights/manifest.jsonl',jsonl(rights));write(out/'rights/THIRD_PARTY_NOTICES.txt',''.join(notices))
    for r in records:write(out/'knowledge'/r['domains'][0]/(r['chunk_id'][7:]+'.md'),r['body_markdown']+'\n\nSource: '+r['origin']['canonical_url']+'\nLicense: '+', '.join(r['rights']['license_ids'])+'; extracted source, code not executed.\n')
    artifacts=[]
    for p in sorted(out.rglob('*')):
        if p.is_file() and not p.name.startswith('._') and p.name not in ['manifest.json','SHA256SUMS']:
            rel=p.relative_to(out).as_posix();artifacts.append({'id':digest(rel)[:24],'path':rel,'mime':'application/gzip' if rel.endswith('.gz') else 'text/plain; charset=utf-8','size':p.stat().st_size,'sha256':digest(p.read_bytes())})
    manifest={'schema_version':'1.0','corpus_id':cid,'pipeline_version':VERSION,'source_revision_set':sorted({r['origin']['repository']+'@'+r['origin']['commit'] for r in records}),'accepted_record_counts_by_kind':{'reference':len(records),'documents':len(docs),'skills':0},'coverage_by_domain':{d:sum(d in r['domains'] for r in records) for d in sorted({x for r in records for x in r['domains']})},'known_gaps':['Newly admitted repositories are restricted to reviewed README snapshots','Oversized sections excluded pending structural subchunk adapter','No executed Swift examples','No reviewed skill packs','Semantic search and model inference unavailable'],'verification_summary':{'schema_valid':len(records),'source_verified':len(records),'code_tested':0},'rights_summary':{license:sum(license in r['rights']['license_ids'] for r in records) for license in sorted({license for r in records for license in r['rights']['license_ids']})},'artifacts':artifacts,'reproducibility_inputs':{'extractor':'markdown-it-py 4.0.0','gzip_mtime':0},'minimum_reader_version':'0.1.0','created_at':None}
    writejson(out/'manifest.json',manifest)
    write(out/'SHA256SUMS',''.join(a['sha256']+'  '+a['path']+'\n' for a in artifacts)+digest((out/'manifest.json').read_bytes())+'  manifest.json\n')
    with db:
        db.execute('INSERT OR IGNORE INTO corpus_snapshots VALUES (?,?,?)',(cid,canonical(manifest),'accepted'))
        db.execute('INSERT OR IGNORE INTO publication_outbox VALUES (?,?,?)',(cid,'pending','R2_NOT_ENABLED'))
        db.execute("INSERT OR REPLACE INTO settings VALUES ('active_corpus',?)",(cid,))
    write(ROOT/'corpus/curated/chunks.jsonl',jsonl(records))
    write(ROOT/'config/sources.lock.jsonl',jsonl([s for s in sources if s['status']=='indexed']))
    writejson(ROOT/'corpus/manifests/current.json',manifest)
    shutil.copytree(out/'rights',ROOT/'corpus/licenses',dirs_exist_ok=True,ignore=shutil.ignore_patterns('._*'))
    db.close();return manifest
def status():
    init();db=connect();active=db.execute("SELECT value FROM settings WHERE key='active_corpus'").fetchone()
    result={'classification':'LOCAL_GITHUB_READY' if readjson(STATE/'state/git-status.json') else 'LOCAL_ONLY_READY','corpus_id':active[0] if active else None,'sources':db.execute('SELECT count(*) FROM sources').fetchone()[0],'chunks':db.execute('SELECT count(*) FROM chunks').fetchone()[0],'approved_sources':db.execute('SELECT count(*) FROM source_revisions').fetchone()[0],'paused':(STATE/'state/paused').exists(),'cloud':'DEFERRED_BY_USER','inference':'INFERENCE_NOT_CONFIGURED','semantic_mode':'unavailable','research':readjson(STATE/'state/research-status.json',{'state':'not_run'}),'maintenance':readjson(STATE/'state/last-run.json',None)}
    db.close();return result
def backup():
    init();dest=STATE/'backups'/('corpus-'+datetime.date.today().isoformat()+'.sqlite3');src=connect();target=sqlite3.connect(dest);src.backup(target);assert target.execute('PRAGMA integrity_check').fetchone()[0]=='ok';target.close();src.close()
    for p in sorted((STATE/'backups').glob('corpus-*.sqlite3'))[:-4]:p.unlink()
    return {'backup_sha256':digest(dest.read_bytes()),'integrity':'ok'}
