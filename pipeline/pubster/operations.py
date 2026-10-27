"""Trusted maintenance and frozen-evaluator research controller. No model calls."""
import datetime, json, os, re, shutil, subprocess, sys, time
from pathlib import Path
from zoneinfo import ZoneInfo
from . import core as c

def command(argv,timeout=45):
    r=subprocess.run(argv,cwd=c.ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
    if r.returncode:raise RuntimeError('COMMAND_FAILED_'+Path(argv[0]).name)
    return r.stdout.strip()
def doctor():
    import psutil
    return {'state_free_gib':round(shutil.disk_usage(c.STATE).free/2**30,2),'memory_available_gib':round(psutil.virtual_memory().available/2**30,2),'battery':bool(psutil.sensors_battery() and not psutil.sensors_battery().power_plugged),'python':sys.version.split()[0],'inference_enabled':False,'cloud':'DEFERRED_BY_USER'}
def resources():
    d=doctor()
    if d['state_free_gib']<10:return 'RESOURCE_DEFERRED_DISK'
    managed=sum(p.stat().st_size for folder in ['raw','exports','cache'] for p in (c.STATE/folder).rglob('*') if p.is_file() and not p.name.startswith('._'))
    if managed>20*1024**3:return 'RESOURCE_DEFERRED_DATA_CAP'
    if d['memory_available_gib']<2:return 'RESOURCE_DEFERRED_MEMORY'
    if d['battery']:return 'RESOURCE_DEFERRED_BATTERY'
    try:
        idle=command(['/usr/sbin/ioreg','-c','IOHIDSystem'],10);m=re.search(r'"HIDIdleTime"\s*=\s*(\d+)',idle)
        if not m or int(m[1])/1e9<300:return 'RESOURCE_DEFERRED_ACTIVE_USER'
        thermal=command(['/usr/bin/pmset','-g','therm'],10)
        limits=re.findall(r'(?:CPU_Speed_Limit|CPU_Scheduler_Limit)\s*=\s*(\d+)',thermal)
        if any(int(x)<100 for x in limits):return 'RESOURCE_DEFERRED_THERMAL'
    except RuntimeError:return 'RESOURCE_DEFERRED_UNKNOWN'
    return None

def evaluate(weight=None,suite='regression'):
    path=c.STATE/'evaluator'/('regression.jsonl' if suite=='regression' else 'dev.jsonl')
    if not path.exists():raise RuntimeError('EVALUATOR_NOT_FROZEN')
    tests=c.rows(path);scores=[]
    for case in tests:
        found=c.search(case['query'],limit=10,weight=weight)
        ranks=[i+1 for i,x in enumerate(found) if x['origin']['path']==case['expected_path'] and x['source_id']==case['source_id']]
        scores.append(1/min(ranks) if ranks else 0)
    return {'queries':len(tests),'mrr':sum(scores)/len(scores),'recall_at_10':sum(x>0 for x in scores)/len(scores),'scores':scores,'suite_sha256':c.digest(path.read_bytes())}

def research(dry=False):
    db=c.connect();now=int(time.time());start=int(datetime.datetime.now(ZoneInfo("America/Toronto")).replace(hour=0,minute=0,second=0,microsecond=0).timestamp())
    if db.execute('SELECT count(*) FROM experiments WHERE created_at>=?',(start,)).fetchone()[0]>=2:return {'state':'DAILY_LIMIT'}
    expected=c.readjson(c.STATE/'evaluator/manifest.json',{})
    for name,digest in expected.items():
        if c.digest((c.STATE/'evaluator'/name).read_bytes())!=digest:raise RuntimeError('EVALUATOR_CHANGED')
    if not expected:raise RuntimeError('EVALUATOR_NOT_FROZEN')
    baseline=c.readjson(c.STATE/'state/retrieval.json',{'title_weight':2})['title_weight']
    base=evaluate(baseline);dev=evaluate(baseline,'dev')
    if base['queries']<20:raise RuntimeError('EVALUATION_TOO_SMALL')
    cid=c.status()['corpus_id'];history=[json.loads(r[0]) for r in db.execute('SELECT result_json FROM experiments')]
    seen={x['candidate_weight'] for x in history if x.get('corpus_id')==cid}
    choices=[w for w in [1,4,8,2] if w!=baseline and w not in seen]
    if not choices:return {'state':'NO_ELIGIBLE_HYPOTHESIS'}
    candidate=choices[0];result={'state':'DRY_RUN' if dry else 'REJECTED','hypothesis':'Changing title weight improves source-path retrieval without regression','corpus_id':cid,'baseline_weight':baseline,'candidate_weight':candidate,'baseline_mrr':base['mrr'],'metric':'regression MRR; no per-query regression','model_calls':0}
    if dry:return result
    started=time.monotonic();trial=evaluate(candidate);trialdev=evaluate(candidate,'dev')
    retained=trial['mrr']>base['mrr'] and trialdev['mrr']>=dev['mrr'] and all(x>=y for x,y in zip(trial['scores'],base['scores'])) and time.monotonic()-started<300
    result.update(state='RETAINED' if retained else 'REJECTED',candidate_mrr=trial['mrr'],duration_seconds=round(time.monotonic()-started,3),evaluator_digest=trial['suite_sha256'])
    if retained:c.writejson(c.STATE/'state/retrieval.json',{'title_weight':candidate});c.writejson(c.ROOT/'config/retrieval.json',{'title_weight':candidate})
    eid=c.identity(cid,candidate,baseline,int(time.time()));db.execute('INSERT INTO experiments VALUES(?,?,?)',(eid,now,c.canonical(result)));db.commit();db.close()
    results=c.rows(c.ROOT/'research/results.jsonl') if (c.ROOT/'research/results.jsonl').exists() else []
    results.append(result);c.write(c.ROOT/'research/results.jsonl',''.join(c.canonical(x)+'\n' for x in results[-100:]))
    c.writejson(c.STATE/'state/research-status.json',result);return result

def scan(paths=None):
    paths=paths or [p for folder in ['apps','pipeline','scripts','services','config','corpus','docs','research','packages','evals'] for p in (c.ROOT/folder).rglob('*') if p.is_file() and not any(x in p.parts for x in ['node_modules','.next','out','.wrangler','dist','__pycache__']) and not p.name.startswith('._')]
    verifier=Path.home()/'.local/share/pubster/secrets/password-verifier.json';v=c.readjson(verifier,{})
    scanned=0
    for p in paths:
        if p.stat().st_size>5*1024*1024:raise RuntimeError('GIT_BLOB_LIMIT')
        data=p.read_bytes();scanned+=1
        if any(x.encode() in data for x in [v.get('key_b64',''),v.get('salt_b64','')] if x):raise RuntimeError('SECRET_FOUND')
        if re.search(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)',data):raise RuntimeError('SECRET_FOUND')
    return {'files_scanned':scanned,'result':'passed'}

def managed_snapshot():
    names=['corpus/curated','corpus/manifests','corpus/licenses','config/sources.lock.jsonl','config/retrieval.json','research/results.jsonl']
    files=[]
    for name in names:
        p=c.ROOT/name
        files.extend([x for x in p.rglob('*') if x.is_file() and not x.name.startswith('._')] if p.is_dir() else ([p] if p.exists() else []))
    return {p.relative_to(c.ROOT).as_posix():c.digest(p.read_bytes()) for p in files}
def assert_managed_untouched():
    previous=c.readjson(c.STATE/'state/managed-files.json')
    if previous is not None and managed_snapshot()!=previous:raise RuntimeError('HUMAN_MANAGED_EDITS_REVIEW_REQUIRED')
def sync():
    with c.lock('git-sync'):
        expected=c.readjson(c.ROOT/'config/git-remote.json')
        if not expected:return {'state':'GIT_NOT_CONFIGURED'}
        remote=command(['git','remote','get-url','origin'])
        if remote!=expected['url']:raise RuntimeError('REMOTE_CHANGED')
        info=json.loads(command(['gh','repo','view',expected['repo'],'--json','visibility,nameWithOwner']))
        if info['visibility']!='PRIVATE' or info['nameWithOwner']!=expected['repo']:raise RuntimeError('PRIVATE_REPOSITORY_REQUIRED')
        if command(['git','branch','--show-current'])!='main':raise RuntimeError('GIT_BRANCH_REVIEW_REQUIRED')
        if command(['git','diff','--cached','--name-only']):raise RuntimeError('HUMAN_STAGED_CHANGES')
        # Abort on any edits not provably generated by this pipeline in this tick.
        allowed=['corpus/curated/','corpus/manifests/','corpus/licenses/','config/sources.lock.jsonl','config/retrieval.json','research/results.jsonl']
        dirty=command(['git','status','--porcelain','--untracked-files=all']).splitlines()
        if any(not any(line[3:].startswith(a) for a in allowed) for line in dirty):raise RuntimeError('HUMAN_WORKTREE_REVIEW_REQUIRED')
        command(['git','fetch','origin','main'],60)
        local=command(['git','rev-parse','HEAD']);remote_sha=command(['git','rev-parse','origin/main'])
        if local!=remote_sha:
            check=subprocess.run(['git','merge-base','--is-ancestor','origin/main','HEAD'],cwd=c.ROOT,capture_output=True)
            if check.returncode:raise RuntimeError('GIT_DIVERGED')
        assert_managed_untouched()
        changed=[c.ROOT/line[3:] for line in dirty if (c.ROOT/line[3:]).is_file()]
        scan(changed)
        if dirty:
            names=[line[3:] for line in dirty];command(['git','add','--',*names]);command(['git','commit','-m','corpus: refresh validated sources and bounded research results'])
        if dirty or local!=remote_sha:command(['git','push','origin','HEAD:main'],90)
        sha=command(['git','rev-parse','HEAD']);actual=command(['git','ls-remote','origin','refs/heads/main']).split()[0]
        if sha!=actual:raise RuntimeError('REMOTE_SHA_MISMATCH')
        result={'state':'synced' if dirty or local!=remote_sha else 'unchanged','commit':sha,'visibility':'PRIVATE'};c.writejson(c.STATE/'state/git-status.json',result);return result

def run():
    c.init();started=time.monotonic()
    try:
        with c.lock():
            if (c.STATE/'state/paused').exists():return {'state':'SKIPPED_PAUSED'}
            assert_managed_untouched()
            result={'started_at':int(time.time()),'model_calls':0,'cloud':'DEFERRED_BY_USER'}
            deferred=resources()
            if deferred:result['ingestion']={'state':deferred}
            else:
                try:
                    result['ingestion']=c.ingest()
                    if result['ingestion']['changed_sources']:result['corpus_id']=c.export()['corpus_id']
                    db=c.connect()
                    records=[json.loads(r[0]) for r in db.execute('SELECT record_json FROM chunks ORDER BY chunk_id')]
                    db.close()
                    result['quality']=c.quality_gate(records)
                    result['backup']=c.backup()
                    result['research']=research()
                except Exception as e:result['pipeline_error']=str(e)[:100] if isinstance(e,RuntimeError) else type(e).__name__
            c.writejson(c.STATE/'state/managed-files.json',managed_snapshot())
            try:result['git']=sync()
            except Exception as e:result['git']={'state':str(e)[:100] if isinstance(e,RuntimeError) else type(e).__name__}
            if result.get('git',{}).get('state') in ['synced','unchanged']:
                try:result['release']=json.loads(command([sys.executable,str(c.ROOT/'scripts/export-release.py')],90))
                except Exception as e:result['release']={'state':'PENDING','error':type(e).__name__}
            result['duration_seconds']=round(time.monotonic()-started,2);c.writejson(c.STATE/'state/last-run.json',result);return result
    except RuntimeError as e:
        if str(e)=='SKIPPED_ALREADY_RUNNING':return {'state':str(e)}
        raise

def dispatch(a):
    c.init()
    if a.command=='doctor':return doctor()
    if a.command=='run':return run()
    if a.command=='security':return scan()
    if a.command=='evaluate':return evaluate(suite='dev' if a.suite=='dev' else 'regression')
    if a.command=='research':return research(a.dry_run) if a.action=='run-one' else {'frozen_evaluator':bool(c.readjson(c.STATE/'evaluator/manifest.json')),'editable_fields':['title_weight'],'arbitrary_code_execution':False,'max_experiments_daily':2,'model_calls':0}
    if a.command in ['sync-github','verify-github']:return sync()
    if a.command=='scheduler':
        alljobs=json.loads(command(['openclaw','automations','list','--all','--json']))
        return {'jobs':[j for j in alljobs.get('jobs',[]) if j.get('name')=='Pubster hourly maintenance']}
    raise RuntimeError('COMMAND_NOT_IMPLEMENTED')
