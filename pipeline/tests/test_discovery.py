import unittest
from unittest.mock import patch
from pubster import discovery as d
class DiscoveryTests(unittest.TestCase):
 def test_repo_validation(self):
  for value in ['../secret','https://evil.example/a/b','a/b?x=1','a/b/c','a/b\n']:
   with self.assertRaises(ValueError): d.repo_id(value)
  self.assertEqual(d.repo_id('https://github.com/apple/swift-algorithms'),'apple/swift-algorithms')
 def test_private_seed_stops_before_external_discovery(self):
  with patch.object(d.Client,'get',return_value={'private':True}), patch.object(d.urllib.request,'urlopen') as network:
   with self.assertRaisesRegex(RuntimeError,'PUBLIC_REPOSITORY_REQUIRED'):d.discover('owner/private','Swift')
   network.assert_not_called()
 def test_code_search_remains_scoped(self):
  client=d.Client()
  with patch.object(client,'get',return_value={'items':[]}) as get:
   d.implementations(client,'apple/swift-algorithms','x repo:secret/private')
   query=d.urllib.parse.parse_qs(d.urllib.parse.urlparse(get.call_args.args[0]).query)['q'][0]
   self.assertEqual(query.count('repo:'),1)
   self.assertTrue(query.endswith('repo:apple/swift-algorithms'))
 def test_budget_blocks_network(self):
  client=d.Client();client.calls=18
  with patch.object(d.subprocess,'run') as run:
   with self.assertRaisesRegex(RuntimeError,'DISCOVERY_BUDGET'):client.get('repos/apple/swift-algorithms')
   run.assert_not_called()
 def test_ranking_does_not_approve_sources(self):
  result=d.summary({'full_name':'a/b','html_url':'https://github.com/a/b','description':'Swift collections','license':{'spdx_id':'MIT'}},'Swift')
  self.assertEqual(result['rights'],'UNREVIEWED');self.assertEqual(result['security'],'NOT_AUDITED');self.assertEqual(result['matched_terms'],['swift'])
