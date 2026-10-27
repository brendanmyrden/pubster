import copy
import importlib.util
import json
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('engine',Path(__file__).with_name('engine.py'))
engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)

class QualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records=[json.loads(x) for x in (engine.ROOT/'corpus/curated/chunks.jsonl').read_text().splitlines()][:8]

    def test_preserves_originals_and_reports_exact_duplicates(self):
        records=copy.deepcopy(self.records)
        duplicate=copy.deepcopy(records[0]);duplicate['chunk_id']='sha256:'+'f'*64
        records.append(duplicate)
        before=copy.deepcopy(records)
        report,frame=engine.analyze(records)
        self.assertEqual(records,before)
        self.assertTrue(report['exact_duplicate_groups'])
        self.assertTrue(report['near_duplicates'])
        self.assertEqual(report['source_mutations'],0)
        self.assertTrue(all(report['great_expectations']))

    def test_duplicate_identity_rejected(self):
        records=copy.deepcopy(self.records);records.append(copy.deepcopy(records[0]))
        with self.assertRaises(Exception):engine.analyze(records)

    def test_unapproved_rights_rejected(self):
        records=copy.deepcopy(self.records);records[0]['rights']['status']='unknown'
        with self.assertRaises(Exception):engine.analyze(records)

    def test_invalid_span_rejected(self):
        records=copy.deepcopy(self.records);records[0]['origin']['line_end']=0
        with self.assertRaisesRegex(ValueError,'INVALID_LINE_SPAN'):engine.analyze(records)

    def test_failed_input_quarantined(self):
        records=copy.deepcopy(self.records);records[0]['rights']['status']='unknown'
        p=engine.STORE/'tmp/test-bad-input.jsonl';p.write_text('\n'.join(json.dumps(x) for x in records))
        with self.assertRaises(Exception):engine.run(p)
        self.assertTrue(any((engine.STORE/'quarantine').glob('*/original.jsonl')))
        self.assertEqual(json.loads(p.read_text().splitlines()[0])['rights']['status'],'unknown')

if __name__=='__main__':unittest.main()
