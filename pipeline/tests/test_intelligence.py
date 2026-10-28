import base64, copy, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from pubster import core as c, discovery
from pubster.intelligence import engine as e, ranking as r
from pubster.intelligence.store import Store
from pubster.intelligence.operator import record

SHA='a'*40

def repo(name='example/queue',stars=14,archived=False):
 return {'full_name':name,'html_url':'https://github.com/'+name,'private':False,'visibility':'public','description':'bounded task queue concurrency','language':'Swift','created_at':'2020-01-01T00:00:00Z','stargazers_count':stars,'forks_count':1,'default_branch':'main','archived':archived,'license':{'spdx_id':'MIT'},'topics':['concurrency']}

class FakeClient:
 def __init__(self):self.calls=0;self.paths=[]
 def get(self,path):
  self.calls+=1;self.paths.append(path)
  if path.startswith('search/repositories'):return {'items':[repo('example/queue'),repo('other/scheduler',100)]}
  if path.startswith('search/code'):return {'items':[{'repository':repo(),'html_url':'https://github.com/example/queue/blob/'+SHA+'/Sources/Queue.swift'}]}
  if path.startswith('search/issues'):return {'items':[{'html_url':'https://github.com/example/queue/issues/1','body':'https://github.com/example/queue'}]}
  if path.startswith('graphql'):return {'data':{'repository':{'discussions':{'nodes':[{'url':'https://github.com/example/queue/discussions/1','body':'https://github.com/example/queue'}]}}}}
  if '/git/trees/' in path:return {'tree':[{'path':'Sources/Queue.swift','type':'blob','size':100,'sha':'b'*40},{'path':'Package.swift','type':'blob','size':100,'sha':'c'*40},{'path':'Tests/QueueTests.swift','type':'blob','size':100,'sha':'d'*40},{'path':'README.md','type':'blob','size':100,'sha':'e'*40}]}
  if '/git/blobs/' in path:return {'encoding':'base64','content':base64.b64encode(b'public struct Queue { }\n// https://github.com/example/dependency').decode()}
  if '/commits/' in path:return {'sha':SHA,'commit':{'committer':{'date':'2026-10-28T01:00:00Z'}}}
  if '/compare/' in path:return {'ahead_by':3,'html_url':'https://github.com/example/queue/compare/main...fork:main'}
  if '/forks?' in path:return [{**repo('fork/queue'),'owner':{'login':'fork'}}]
  if '/contributors?' in path:return [{'login':'example'}]
  if '/releases?' in path:return [{'html_url':'https://github.com/example/queue/releases/tag/1','body':'https://github.com/example/dependency'}]
  if path.startswith('users/'):return [repo()]
  if path.startswith('repos/'):return repo(path.removeprefix('repos/'))
  raise AssertionError(path)

class IntelligenceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=c.ROOT/'.quality');self.root=Path(self.tmp.name)
  self.cfg=e.config();(self.root/'config').mkdir();(self.root/'research/discovery').mkdir(parents=True)
  c.writejson(self.root/'config/intelligence.json',self.cfg)
  c.writejson(self.root/'config/rights-policy.json',{'approved_repositories':['approved/root']})
  self.patch=patch.object(c,'ROOT',self.root);self.patch.start();self.statepatch=patch.object(c,'STATE',self.root/'state');self.statepatch.start();self.store=Store()
 def tearDown(self):self.store.close();self.statepatch.stop();self.patch.stop();self.tmp.cleanup()
 def test_all_modes_generate_candidates_with_public_adapters(self):
  with patch.object(discovery,'Client',FakeClient),patch.object(e.CachedClient,'papers',return_value=[{'title':'queue paper','url':'https://arxiv.org/abs/1','implementations':['example/queue']}]):
   for mode in e.MODES:
    result=e.run('approved/root','Swift concurrency',mode=mode)
    self.assertTrue(result['candidates'],mode)
    self.assertLessEqual(result['github_requests'],18)
    self.assertEqual(result['mode'],mode)
    for item in result['candidates']:
     self.assertEqual(item['rights'],'UNREVIEWED');self.assertNotEqual(item['evidence_status'],'Verified')
 def test_every_graph_and_context_adapter_produces_candidates(self):
  client=e.CachedClient(self.store,self.cfg,FakeClient())
  with patch.object(client,'papers',return_value=[{'url':'https://arxiv.org/abs/1','title':'queue','implementations':['example/queue']}]):
   for kind in e.TECHNIQUES:
    # Independent scan budgets; cached source relationships remain shared.
    client=e.CachedClient(self.store,self.cfg,FakeClient())
    with patch.object(client,'papers',return_value=[{'url':'https://arxiv.org/abs/1','title':'queue','implementations':['example/queue']}]):
     found={};e.execute({'kind':kind,'seed':'approved/root','query':'bounded queue','symbol':'enqueue'},client,self.store,found,self.cfg)
     self.assertTrue(found,kind)
 def test_claimed_benchmarks_and_stars_do_not_create_power(self):
  a=repo();a['description']='1000x faster revolutionary benchmark'
  low=r.score(a,{},self.cfg,[],'Swift concurrency')
  a['stargazers_count']=50000;high=r.score(a,{},self.cfg,[],'Swift concurrency')
  self.assertEqual(low['score'],high['score']);self.assertEqual(high['score_components']['power']['points'],0)
 def test_underexposure_comparable_cohort_and_independent_usefulness(self):
  peers=[{**repo('peer/'+str(i),100+i),'purpose_concept':'concurrency'} for i in range(3)]
  inspection={'files':[{'kind':'source','read':True,'path':'Queue.swift'}]}
  score=r.score(repo(),inspection,self.cfg,peers,'Swift concurrency')
  self.assertEqual(score['score_components']['underexposure']['points'],10)
  self.assertEqual(score['score_components']['usefulness']['points'],3)
  peers[0]['language']='Rust';self.assertEqual(r.score(repo(),inspection,self.cfg,peers,'Swift concurrency')['score_components']['underexposure']['points'],0)
 def test_archive_does_not_reduce_value_score(self):
  self.assertEqual(r.score(repo(),{},self.cfg,[],'queue')['score'],r.score(repo(archived=True),{},self.cfg,[],'queue')['score'])
 def test_two_levels_and_commit_pinned_evidence(self):
  inspected=e.inspect(e.CachedClient(self.store,self.cfg,FakeClient()),repo())
  item=r.candidate(repo(),inspected,self.cfg,[],'Swift concurrency','hidden-gems')
  self.assertTrue(item['capabilities']);self.assertEqual(item['revision'],SHA)
  self.assertIn(SHA,item['source_files'][0]['url']);self.assertEqual(item['evidence_status'],'Source-supported')
  self.assertFalse(inspected['executed'])
 def test_unchanged_commit_reuses_inspection_but_rescores_context(self):
  with patch.object(discovery,'Client',FakeClient),patch.object(e,'inspect',wraps=e.inspect) as inspect:
   e.run('approved/root','Swift concurrency',mode='hidden-gems');first=inspect.call_count
   self.store.setmeta('rotation',0)
   e.run('approved/root','Swift executor',mode='hidden-gems')
   self.assertEqual(inspect.call_count,first)
 def test_cache_and_strict_request_budget(self):
  cfg={**self.cfg,'max_requests':1};base=FakeClient();client=e.CachedClient(self.store,cfg,base)
  client.get('repos/example/one');client.get('repos/example/one')
  self.assertEqual(base.calls,1);self.assertEqual(client.hits,1)
  with self.assertRaisesRegex(RuntimeError,'DISCOVERY_BUDGET'):client.get('repos/example/two')
 def test_byte_budget(self):
  cfg={**self.cfg,'max_response_bytes':10};client=e.CachedClient(self.store,cfg,FakeClient())
  with self.assertRaisesRegex(RuntimeError,'RESPONSE_TOO_LARGE'):client.get('repos/example/one')
 def test_score_version_reuse_rejected_and_history_preserved(self):
  self.store.register(self.cfg);changed=copy.deepcopy(self.cfg);changed['weights']['power']-=1;changed['weights']['usefulness']+=1
  with self.assertRaisesRegex(RuntimeError,'SCORING_VERSION_REUSE_FORBIDDEN'):self.store.register(changed)
  changed['scoring_version']='capability-v2';self.store.register(changed)
  self.assertEqual(self.store.db.execute('SELECT count(*) FROM criteria').fetchone()[0],2)
 def test_resume_cursor_survives_new_connection(self):
  scan=self.store.begin('id','hidden-gems',[{'kind':'search'},{'kind':'forks'}]);self.store.checkpoint(scan['id'],1,{'example/queue':{}},[],{'requests':2})
  other=Store(self.store.path)
  try:
   resumed=other.begin('id','adjacency',[])
   self.assertEqual(resumed['id'],scan['id']);self.assertEqual(resumed['cursor'],1);self.assertEqual(resumed['mode'],'hidden-gems')
  finally:other.close()
 def test_interrupted_scan_resumes_without_repeating_completed_task(self):
  original=e.execute;calls=[]
  def interrupt(task,*args):
   calls.append(task['kind'])
   if len(calls)==2:raise KeyboardInterrupt()
   return original(task,*args)
  with patch.object(discovery,'Client',FakeClient),patch.object(e,'execute',side_effect=interrupt):
   with self.assertRaises(KeyboardInterrupt):e.run('approved/root','Swift concurrency')
  row=self.store.db.execute('SELECT cursor FROM scans').fetchone();self.assertEqual(row[0],1)
  with patch.object(discovery,'Client',FakeClient),patch.object(e,'execute',wraps=original) as execute:
   result=e.run('approved/root','Swift concurrency')
   self.assertEqual(result['state'],'COMPLETE');self.assertEqual(execute.call_count,2)
 def test_graph_cycles_hop_limit_and_frontier_cap(self):
  self.store.seed('a/root');self.store.edge('a/root','a/root','b/dep','dependency',1,{})
  self.store.edge('a/root','b/dep','a/root','dependency',2,{})
  self.store.edge('a/root','b/dep','c/far','dependency',4,{})
  self.assertEqual(self.store.db.execute('SELECT count(*) FROM frontier').fetchone()[0],2)
  self.store.edge('a/root','b/dep','d/other','dependency',2,{},limit=2)
  self.assertEqual(self.store.db.execute('SELECT count(*) FROM frontier').fetchone()[0],2)
 def test_migration_preserves_exact_legacy_bytes(self):
  path=self.root/'research/discovery/old.json';path.write_text('{"review":"approved"}\n');original=path.read_bytes()
  self.store.migrate(path.parent);self.store.migrate(path.parent)
  self.assertEqual(path.read_bytes(),original);self.assertTrue((self.store.path.parent/'legacy-v1'/(c.digest(original)+'.json')).exists())
 def test_review_gates_do_not_modify_corpus(self):
  item=r.candidate(repo(),{'revision':SHA},self.cfg,[],'queue','hidden-gems');self.store.save(item)
  entry={'repository':'example/queue','revision':SHA,'kind':'approved','actor':'test','rationale':'test'}
  with self.assertRaises(ValueError):record(self.store,entry,self.cfg)
  record(self.store,{**entry,'kind':'reviewed'},self.cfg)
  with self.assertRaises(ValueError):record(self.store,{**entry,'kind':'verified','evidence':[{'url':'https://example.org','status':'Claimed','rationale':'README says so'}]},self.cfg)
  ev=[{'url':'https://example.org/report','status':'Verified','rationale':'independent source inspection'}]
  record(self.store,{**entry,'kind':'verified','evidence':ev},self.cfg)
  self.assertFalse(record(self.store,{**entry,'license_review':'MIT inspected'},self.cfg)['corpus_modified'])
  self.assertFalse((self.root/'state/pubster.sqlite3').exists())
 def test_private_candidates_are_filtered(self):
  found={};e.add_repo(found,{**repo(),'private':True},{})
  self.assertEqual(found,{})
 def test_feedback_does_not_mutate_criteria(self):
  self.store.save(r.candidate(repo(),{'revision':SHA},self.cfg,[],'queue','hidden-gems'))
  before=(self.root/'config/intelligence.json').read_bytes()
  result=record(self.store,{'repository':'example/queue','revision':SHA,'kind':'feedback','actor':'test','rationale':'Prefer bounded queues'},self.cfg)
  self.assertFalse(result['criteria_changed']);self.assertEqual((self.root/'config/intelligence.json').read_bytes(),before)

 def test_request_audit_survives_failure(self):
  base=FakeClient()
  with patch.object(base,'get',side_effect=RuntimeError('GITHUB_UNAVAILABLE_OR_RATE_LIMITED')):
   with self.assertRaises(RuntimeError):e.CachedClient(self.store,self.cfg,base).get('repos/example/queue')
  self.assertEqual(self.store.metrics()['failed_or_interrupted_requests'],1)
 def test_rejected_requires_fresh_review_before_verification(self):
  item=r.candidate(repo(),{'revision':SHA},self.cfg,[],'queue','hidden-gems');self.store.save(item)
  entry={'repository':'example/queue','revision':SHA,'actor':'test','rationale':'evidence','evidence':[{'url':'https://example.org/review','status':'Verified','rationale':'inspected'}]}
  for kind in ['reviewed','verified','rejected']:record(self.store,{**entry,'kind':kind},self.cfg)
  with self.assertRaises(ValueError):record(self.store,{**entry,'kind':'approved','license_review':'MIT'},self.cfg)
  with self.assertRaises(ValueError):record(self.store,{**entry,'kind':'verified'},self.cfg)
 def test_feedback_query_is_sanitized_and_keeps_weights(self):
  self.store.save(r.candidate(repo(),{'revision':SHA},self.cfg,[],'queue','hidden-gems'))
  record(self.store,{'repository':'example/queue','revision':SHA,'kind':'feedback','actor':'test','rationale':'better intent','purpose_concept':'concurrency','search_terms':'bounded queue repo:private/secret'},self.cfg)
  tasks,_=e.plan('approved/root','Swift concurrency','hidden-gems',self.cfg,0,self.store)
  self.assertNotIn('repo:',tasks[1]['query']);self.assertTrue(tasks[1]['query'].endswith('is:public'))

 def test_review_evidence_changes_future_rankings_without_changing_weights(self):
  with patch.object(discovery,'Client',FakeClient):
   result=e.run('approved/root','Swift concurrency',mode='hidden-gems')
   item=next(x for x in result['candidates'] if x.get('revision'))
   entry={'repository':item['repository'],'revision':item['revision'],'kind':'reviewed','actor':'test','rationale':'mechanism inspected','assessment':{'mechanism_reviewed':True},'evidence':[{'url':item['source_files'][0]['url'],'status':'Source-supported','rationale':'inspected source'}]}
   record(self.store,entry,self.cfg);self.store.setmeta('rotation',0)
   updated=e.run('approved/root','Swift concurrency',mode='hidden-gems')
   actual=next(x for x in updated['candidates'] if x['repository']==item['repository'])
   self.assertGreater(actual['score_components']['power']['points'],item['score_components']['power']['points'])
   self.assertEqual(actual['stage'],'Reviewed')

if __name__=='__main__':unittest.main()
