import json,os,sqlite3,sys,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pubster import core as c
from pubster import operations as op
class PipelineTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.old=c.STATE;c.STATE=Path(self.temp.name);c.init()
 def tearDown(self):c.STATE=self.old;self.temp.cleanup()
 def test_registry_count_and_identity(self):
  db=c.connect();self.assertEqual(db.execute('SELECT count(*) FROM sources').fetchone()[0],sum(len(c.rows(c.ROOT/'config'/p)) for p in ['sources.seed.jsonl','sources.supplemental.jsonl']));self.assertEqual(db.execute("SELECT count(*) FROM sources WHERE source_id LIKE 'atlas-%'").fetchone()[0],100);db.close()
 def chunks(self):
  text='# Bounded example\n\nUse cancellation.\n\n```swift\nlet task = Task { 42 }\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n@Tutorial { reference }\n';return text,c.chunk_markdown(text,{'source_id':'atlas-015','domain':'algorithms'},'apple/swift-algorithms','a'*40,'Guides/Test.md','evidence')
 def test_structural_spans_preserve_code_tables_directives(self):
  text,records=self.chunks();self.assertEqual(len(records),1);self.assertEqual(records[0]['body_markdown'],text.strip());self.assertIn('```swift',records[0]['body_markdown']);self.assertIn('@Tutorial',records[0]['body_markdown']);self.assertEqual(records,c.chunk_markdown(text,{'source_id':'atlas-015','domain':'algorithms'},'apple/swift-algorithms','a'*40,'Guides/Test.md','evidence'))
 def test_fts_insert_update_delete(self):
  _,records=self.chunks();db=c.connect();c.store_chunk(db,records[0]);db.commit();self.assertEqual(len(c.search('cancellation')),1);db.execute("UPDATE chunks SET body_text='uniquechangedword',title='changed' WHERE source_id='atlas-015'");db.commit();self.assertEqual(len(c.search('cancellation')),0);self.assertEqual(db.execute("SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH 'uniquechangedword'").fetchone()[0],1);db.execute('DELETE FROM chunks');db.commit();self.assertEqual(db.execute("SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH 'uniquechangedword'").fetchone()[0],0);db.close()
 def test_sql_query_and_fts_syntax_are_inert(self):
  for q in ['" OR *','NEAR((()))','x\"; DROP TABLE chunks;--','a'*1000]:self.assertEqual(c.search(q),[])
 def test_provenance_detects_tamper(self):
  text,records=self.chunks();db=c.connect();db.execute('INSERT INTO license_evidence VALUES(?,?,?,?)',('evidence','atlas-015',c.digest(b'license'),'{}'));db.commit();c.write(c.STATE/'raw'/c.digest(text),text);self.assertEqual(c.validate_records(records,db),1);records[0]['body_markdown']='tampered';self.assertRaises(AssertionError,c.validate_records,records,db);db.close()
 def test_quality_failure_prevents_export_publication(self):
  text,records=self.chunks();db=c.connect();db.execute('INSERT INTO license_evidence VALUES(?,?,?,?)',('evidence','atlas-015',c.digest(b'license'),'{}'));c.store_chunk(db,records[0]);db.commit();db.close();c.write(c.STATE/'raw'/c.digest(text),text)
  with patch.object(c,'quality_gate',side_effect=RuntimeError('QUALITY_GATE_FAILED')):
   with self.assertRaisesRegex(RuntimeError,'QUALITY_GATE_FAILED'):c.export()
  self.assertIsNone(c.status()['corpus_id']);self.assertEqual(list((c.STATE/'exports').iterdir()),[])
 def test_url_allowlist(self):
  f=c.Fetcher()
  for url in ['http://api.github.com','https://127.0.0.1/','https://user@api.github.com/','https://api.github.com:443/','https://evil.example/']:
   self.assertRaises(ValueError,f.get,url)
 def test_overlap_lock(self):
  with c.lock():
   with self.assertRaisesRegex(RuntimeError,'SKIPPED_ALREADY_RUNNING'):
    with c.lock():pass
 def test_pause_resume(self):
  c.write(c.STATE/'state/paused','paused');self.assertEqual(op.run()['state'],'SKIPPED_PAUSED');(c.STATE/'state/paused').unlink();self.assertFalse(c.status()['paused'])
 def test_backup_integrity(self):
  self.assertEqual(c.backup()['integrity'],'ok');db=sqlite3.connect(next((c.STATE/'backups').glob('*.sqlite3')));self.assertEqual(db.execute('SELECT count(*) FROM sources').fetchone()[0],sum(len(c.rows(c.ROOT/'config'/p)) for p in ['sources.seed.jsonl','sources.supplemental.jsonl']));db.close()
 def test_sync_requires_explicit_matching_visibility(self):
  expected={'repo':'owner/repo','url':'https://github.com/owner/repo.git','visibility':'PUBLIC'}
  def command(args,*rest):
   if args[:3]==['git','remote','get-url']:return expected['url']
   if args[0]=='gh':return json.dumps({'visibility':visibility,'nameWithOwner':'owner/repo'})
   if args[:2]==['git','branch']:return 'main'
   if args[:2]==['git','rev-parse']:return 'abc'
   if args[:2]==['git','ls-remote']:return 'abc refs/heads/main'
   return ''
  with patch.object(c,'readjson',return_value=expected),patch.object(op,'command',side_effect=command),patch.object(op,'assert_managed_untouched'),patch.object(op,'scan'):
   visibility='PUBLIC'
   self.assertEqual(op.sync()['visibility'],'PUBLIC')
   visibility='PRIVATE'
   with self.assertRaisesRegex(RuntimeError,'VISIBILITY_MISMATCH'):op.sync()
 def test_command_preserves_git_porcelain_leading_spaces(self):
  from types import SimpleNamespace
  with patch.object(op.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=' M research/discovery/latest.json\n',stderr='')):
   self.assertEqual(op.command(['git','status','--porcelain']), ' M research/discovery/latest.json')
 def test_reviewed_license_hash_blocks_changes_and_preserves_mit(self):
  body=b'Permission is hereby granted, free of charge THE SOFTWARE IS PROVIDED'
  c.verify_license(body,'MIT',c.digest(body))
  with self.assertRaisesRegex(RuntimeError,'LICENSE_CHANGED_REVIEW_REQUIRED'):c.verify_license(body+b' changed','MIT',c.digest(body))
  with self.assertRaisesRegex(RuntimeError,'LICENSE_MISMATCH'):c.verify_license(body,'Unknown')
  records=c.chunk_markdown('# Example\n\n'+'Reviewed content. '*10,{'source_id':'x','domain':'learning-tooling','rights':{'spdx_expression':'MIT'}},'owner/repo','a'*40,'README.md','evidence')
  self.assertEqual(records[0]['rights']['license_ids'],['MIT'])
 def test_export_preserves_mit_attribution(self):
  text,records=self.chunks();records[0]['rights']['license_ids']=['MIT']
  db=c.connect();source=json.loads(db.execute("SELECT record_json FROM sources WHERE source_id='atlas-015'").fetchone()[0]);source['rights']['spdx_expression']='MIT'
  db.execute("UPDATE sources SET record_json=? WHERE source_id='atlas-015'",(c.canonical(source),))
  db.execute('INSERT INTO license_evidence VALUES(?,?,?,?)',('evidence','atlas-015',c.digest(b'license'),c.canonical({'LICENSE':'MIT license text'})))
  c.store_chunk(db,records[0]);db.commit();db.close();c.write(c.STATE/'raw'/c.digest(text),text)
  with patch.object(c,'quality_gate',return_value={'state':'accepted'}), patch.object(c,'ROOT',Path(self.temp.name)/'project'), patch.object(c,'validate_records',return_value=1):result=c.export()
  self.assertEqual(result['rights_summary'],{'MIT':1})
  out=c.STATE/'exports'/result['corpus_id']
  self.assertEqual(c.rows(out/'rights/manifest.jsonl')[0]['license'],'MIT')
  self.assertIn('License: MIT;',next(p for p in (out/'knowledge').rglob('*.md') if not p.name.startswith('._')).read_text())
if __name__=='__main__':unittest.main()
