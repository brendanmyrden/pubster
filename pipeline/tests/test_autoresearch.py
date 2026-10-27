import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from pubster import core as c
from pubster import autoresearch as ar
from pubster import operations as op

def envelope(proposal):
 return {'ok':True,'provider':'openai','model':'gpt-6-astra','outputs':[{'text':json.dumps(proposal)}]}
OAUTH={'auth':{'providers':[{'provider':'openai','effective':{'kind':'profiles'},'profiles':{'oauth':1,'apiKey':0,'token':0}}]}}
class AutoresearchTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.oldroot=c.ROOT;self.oldstate=c.STATE;self.oldar=ar.STATE
  c.ROOT=Path(self.temp.name);c.STATE=c.ROOT/'state';ar.STATE=c.ROOT/'.quality/autoresearch'
  c.writejson(c.ROOT/'config/autoresearch.json',{'enabled':True})
  c.write(c.ROOT/'research/program.md','Return numeric proposal only.')
  c.write(c.ROOT/'host-config','original')
  c.writejson(ar.STATE/'host-guard.json',{'path':str(c.ROOT/'host-config'),'sha256':c.digest('original')})
  c.write(c.STATE/'evaluator/test.json','fixed')
  c.writejson(c.STATE/'evaluator/manifest.json',{'test.json':c.digest('fixed')})
 def tearDown(self):
  c.ROOT=self.oldroot;c.STATE=self.oldstate;ar.STATE=self.oldar;self.temp.cleanup()
 def test_rejects_non_numeric_extra_keys_and_repeated_proposals(self):
  for p in [{'title_weight':True,'hypothesis':'x'},{'title_weight':float('nan'),'hypothesis':'x'},{'title_weight':2,'hypothesis':'x'},{'title_weight':3.1,'hypothesis':'x'},{'title_weight':3,'hypothesis':'x','shell':'bad'}]:
   with self.assertRaises(RuntimeError):ar.parse_proposal(envelope(p),2,{4})
  self.assertEqual(ar.parse_proposal(envelope({'title_weight':3,'hypothesis':'x'}),2,{4})['title_weight'],3)
 def test_requires_oauth_not_api_key(self):
  ar.require_oauth(OAUTH)
  with self.assertRaises(RuntimeError):ar.require_oauth({'auth':{'providers':[]}})
  bad=json.loads(json.dumps(OAUTH));bad['auth']['providers'][0]['profiles']['apiKey']=1
  with self.assertRaises(RuntimeError):ar.require_oauth(bad)
 def test_shared_config_drift_blocks(self):
  ar.host_guard();c.write(c.ROOT/'host-config','modified')
  with self.assertRaisesRegex(RuntimeError,'CONFIG_CHANGED'):ar.host_guard()
 def test_failed_attempt_consumes_daily_slot(self):
  self.assertTrue(ar.reserve_call());self.assertFalse(ar.reserve_call())
 def test_configured_limit_preserves_used_slots_and_blocks_fifth(self):
  self.assertTrue(ar.reserve_call())
  c.writejson(c.ROOT/'config/autoresearch.json',{'enabled':True,'max_proposals_daily':4})
  c.writejson(c.ROOT/'config/budget-policy.json',{'research_max_model_calls_daily':4})
  for _ in range(3):self.assertTrue(ar.reserve_call())
  self.assertFalse(ar.reserve_call())
  self.assertEqual(c.readjson(ar.STATE/'calls.json')['calls'],4)
 def test_lower_budget_limit_and_invalid_limits(self):
  c.writejson(c.ROOT/'config/autoresearch.json',{'max_proposals_daily':4})
  self.assertEqual(ar.daily_limit(),1)
  c.writejson(c.ROOT/'config/budget-policy.json',{'research_max_model_calls_daily':0})
  self.assertFalse(ar.reserve_call())
  for value in [True,-1,1.5,'4']:
   c.writejson(c.ROOT/'config/budget-policy.json',{'research_max_model_calls_daily':value})
   with self.assertRaisesRegex(RuntimeError,'INVALID_RESEARCH_DAILY_LIMIT'):ar.reserve_call()
 def test_previous_day_resets_count(self):
  c.writejson(ar.STATE/'calls.json',{'date':'2000-01-01','calls':99})
  self.assertTrue(ar.reserve_call())
  self.assertEqual(c.readjson(ar.STATE/'calls.json')['calls'],1)
 def evaluate(self,weight,suite='regression'):
  value=.5 if weight==2 else self.trial
  return {'queries':20,'mrr':value,'scores':[value]*20}
 def execute(self):
  with patch.object(c,'status',return_value={'corpus_id':'testcorpus'}),patch.object(op,'evaluate',side_effect=self.evaluate),patch.object(ar,'cli_json',side_effect=[OAUTH,envelope({'title_weight':3,'hypothesis':'Try more title emphasis.'})]) as cli:
   result=ar.run()
   self.assertEqual(cli.call_count,2)
   args=cli.call_args_list[1].args[0]
   self.assertIn('--local',args);self.assertNotIn('--gateway',args);self.assertNotIn('--deliver',args)
   return result
 def test_regression_rejected_without_changing_active_weight(self):
  self.trial=.4;result=self.execute();self.assertEqual(result['state'],'REJECTED')
  self.assertFalse((c.STATE/'state/retrieval.json').exists())
 def test_strict_improvement_retained(self):
  self.trial=.6;result=self.execute();self.assertEqual(result['state'],'RETAINED')
  self.assertEqual(c.readjson(c.STATE/'state/retrieval.json'),{'title_weight':3})
  self.assertEqual(c.readjson(c.ROOT/'config/retrieval.json'),{'title_weight':3})
 def test_invalid_provider_response_does_not_run_trial(self):
  with patch.object(c,'status',return_value={'corpus_id':'testcorpus'}),patch.object(op,'evaluate',return_value={'queries':20,'mrr':.5,'scores':[.5]*20}) as evaluate,patch.object(ar,'cli_json',side_effect=[OAUTH,{'ok':False}]):
   self.assertEqual(ar.run()['state'],'FAILED');self.assertEqual(evaluate.call_count,2)
 def test_changed_evaluator_blocks_before_provider(self):
  c.write(c.STATE/'evaluator/test.json','changed')
  with patch.object(ar,'cli_json') as cli:
   with self.assertRaisesRegex(RuntimeError,'EVALUATOR_CHANGED'):ar.run()
   cli.assert_not_called()
if __name__=='__main__':unittest.main()
