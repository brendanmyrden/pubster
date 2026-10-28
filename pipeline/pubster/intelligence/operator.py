"""Operator interface. No candidate code execution, rights-policy edits or corpus writes."""
import argparse, json, re
from pathlib import Path
from .. import core as c
from . import engine, ranking
from .store import Store

def record(store,entry,cfg):
    required=['repository','revision','kind','actor','rationale']
    if any(not entry.get(k) for k in required):raise ValueError('Missing review fields')
    if not re.fullmatch('[a-f0-9]{40}',entry['revision']):raise ValueError('Pinned commit required')
    evidence=entry.get('evidence',[])
    if not isinstance(evidence,list):raise ValueError('Evidence must be a list')
    for item in evidence:
        if not isinstance(item,dict) or not item.get('url') or item.get('status') not in ['Verified','Source-supported','Claimed','Speculative'] or not item.get('rationale'):raise ValueError('Evidence needs URL, status and rationale')
    claims=entry.get('assessment',{})
    allowed={'benchmark_reproduced','mechanism_reviewed','use_case_reviewed','integration_success','alternative_comparison','offline_build','executed'}
    if set(claims)-allowed or any(type(v) is not bool for v in claims.values()):raise ValueError('Invalid assessment')
    if any(claims.values()) and not any(e['status'] in ['Verified','Source-supported'] for e in evidence):raise ValueError('Assessment requires independent evidence')
    executed={'benchmark_reproduced','integration_success','offline_build','executed'}
    if any(claims.get(k) for k in executed) and (not any(e['status']=='Verified' for e in evidence) or not entry.get('execution')):raise ValueError('Execution claims require a recorded command/environment/result and verified evidence')
    if any(claims.get(k) for k in executed):
        execution=entry.get('execution')
        if not isinstance(execution,dict) or any(not execution.get(k) for k in ['command','environment','result']):raise ValueError('Execution needs command, environment and result')
    if entry['kind']=='verified' and not any(e['status']=='Verified' for e in evidence):raise ValueError('Verified transition requires independent verified evidence')
    if entry.get('recommendation') not in [None,'investigate','prototype','reference','reject']:raise ValueError('Invalid recommendation')
    for finding in entry.get('capability_findings',[]):
        if finding.get('relationship') not in ['new','improvement','redundant','unknown'] or not finding.get('source_url') or not finding.get('rationale'):raise ValueError('Capability findings need relationship, source URL and rationale')
        if entry['revision'] not in finding['source_url']:raise ValueError('Capability finding must reference this pinned revision')
    # An operator attests to evidence; the engine does not pretend to run their command.
    outcome=store.event(entry['repository'],entry['revision'],entry['kind'],entry['actor'],entry)
    if claims:
        item=store.snapshot(entry['repository'],entry['revision'],cfg['scoring_version'])
        if item:
            inspection=dict(item['inspection']);inspection['review_evidence']=claims
            repo={'full_name':item['repository'],'language':item['language'],'created_at':item.get('created_at'),'stargazers_count':item['stars']}
            item=dict(item);item.update(ranking.score(repo,inspection,cfg,[],item.get('objective',''),item['existing_corpus_overlap']['repository_present']))
            item['review_assessment']=entry;store.evaluation(item)
            outcome['revised_score']=item['score']
    if entry['kind']=='feedback':
        # Feedback produces a proposed query/ranking change, never mutates canonical criteria.
        store.setmeta('feedback-pending:'+str(store.db.execute('SELECT max(id) FROM events').fetchone()[0]),entry)
        outcome['criteria_changed']=False
        if entry.get('search_terms') and entry.get('purpose_concept') in cfg['intent_concepts']:
            store.setmeta('query-feedback:'+entry['purpose_concept'],{'search_terms':engine.safe_words(entry['search_terms']),'actor':entry['actor'],'rationale':entry['rationale']})
            outcome['future_query_updated']=True
    return outcome

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['status','scan','record','history'])
    p.add_argument('--mode',choices=engine.MODES);p.add_argument('--seed');p.add_argument('--objective');p.add_argument('--record');p.add_argument('--repository')
    a=p.parse_args(argv)
    cfg=engine.config()
    with c.lock():
        if a.action=='scan':
            if not a.seed or not a.objective:p.error('scan needs --seed and --objective')
            from .. import operations
            operations.assert_managed_untouched()
            with c.lock('discovery'):
                result=engine.run(a.seed,a.objective,mode=a.mode)
                path=c.ROOT/'research/discovery'/('mode-'+result['mode']+'.json')
                c.writejson(path,result);c.write(path.with_suffix('.md'),engine.report(result))
                c.writejson(c.STATE/'state/managed-files.json',operations.managed_snapshot())
            print(c.canonical({'state':result['state'],'mode':result['mode'],'candidates':len(result['candidates']),'metrics':result['metrics'],'report':str(path)}));return
        store=Store()
        try:
            store.register(cfg)
            if a.action=='status':result={'metrics':store.metrics(),'schema_version':1,'criteria':cfg['scoring_version'],'pending_feedback':store.db.execute("SELECT count(*) FROM meta WHERE key LIKE 'feedback-pending:%'").fetchone()[0]}
            elif a.action=='record':
                if not a.record:p.error('record needs a JSON --record file')
                with c.lock('intelligence-ledger'):
                    result=record(store,json.loads(Path(a.record).read_text()),cfg)
            else:
                if not a.repository:p.error('history needs --repository')
                result={'snapshots':[json.loads(r[0]) for r in store.db.execute('SELECT body FROM snapshots WHERE repository=?',(a.repository.lower(),))],
                  'evaluations':[json.loads(r[0]) for r in store.db.execute('SELECT body FROM evaluations WHERE repository=? ORDER BY at',(a.repository.lower(),))],
                  'events':[dict(r) for r in store.db.execute('SELECT * FROM events WHERE repository=? ORDER BY id',(a.repository.lower(),))]}
            print(c.canonical(result))
        finally:store.close()

if __name__=='__main__':main()
