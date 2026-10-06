import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/jd-app-hot-sales/scripts'
sys.path.insert(0, str(SCRIPTS))
from sales_parser import parse_display
from prepare_input import normalize
from result_store import bind_manifest, classified, load_latest


class WorkflowTests(unittest.TestCase):
    def test_display_boundaries(self):
        for text, hit in [('全网热销99.9万+', False), ('全网热销100万+', True),
                          ('全网热销100万', True), ('全网热销200万+', True),
                          ('全网热销999.9万+', True), ('全网热销1000万+', False),
                          ('全网热销1000万', False), ('全网热销1亿+', False),
                          ('全网热销100w+', True), ('全网热销100万以上', True)]:
            with self.subTest(text=text):
                self.assertIs(parse_display(text)['hit'], hit)

    def test_missing_or_other_metric_never_zero(self):
        for text in ['', None, '评价100万+', '全网热销100万+ 全网热销200万+', '全网热销100万+推荐']:
            self.assertIsNone(parse_display(text))

    def test_title_unknown_cannot_be_promoted(self):
        r = classified({'sku': '111', 'identity_verified': False, 'status': '商品标题不一致待核验',
                        'raw_metric': '全网热销200万+', 'hit': True})
        self.assertIsNone(r['raw_metric'])
        self.assertIsNone(r['hit'])
        self.assertIsNone(r['parsed'])

    def test_changed_rule_reclassifies_verified_observation(self):
        r = classified({'identity_verified': True, 'raw_metric': '全网热销1000万+', 'hit': True})
        self.assertIs(r['hit'], False)

    def test_input_deduplication_and_conflict(self):
        self.assertEqual(normalize([{'SKU编号':'111','商品名称':'A'}])[0]['sku'],'111')
        self.assertEqual(normalize([{'SKU编码':'111','商品名称':'A'}])[0]['sku'],'111')
        self.assertEqual(len(normalize([{'sku': '111','title':'A'}, {'sku':'111','title':'A'}])),1)
        with self.assertRaises(ValueError):
            normalize([{'sku':'111','title':'A'}, {'sku':'111','title':'B'}])
        with self.assertRaises(ValueError):
            normalize([{'sku': 111.5, 'title':'A'}])

    def test_manifest_and_foreign_result_rejected(self):
        records = [{'sku':'111','商品名称':'A'}]
        with tempfile.TemporaryDirectory() as td:
            bind_manifest(td, records)
            bind_manifest(td, records)
            with self.assertRaises(ValueError):
                bind_manifest(td, [{'sku':'222','商品名称':'A'}])
            p = Path(td)/'results.jsonl'
            p.write_text(json.dumps({'sku':'222','identity_verified':False})+'\n')
            with self.assertRaises(ValueError):
                load_latest(p, records)

    def test_all_inputs_above_400_and_resume_without_device(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td)
            records=[{'sku':str(100000000000+i),'商品名称':f'Synthetic {i}',
                      'exclude_reason':'synthetic explicit exclusion'} for i in range(401)]
            records += [{'sku':'999000000001','商品名称':'Same'}, {'sku':'999000000002','商品名称':'Same'}]
            source=td/'input.json'
            source.write_text(json.dumps({'records':records}),encoding='utf-8')
            args=[sys.executable,str(SCRIPTS/'collect.py'),'--input',str(source),
                  '--output-dir',str(td/'run'),'--serial','synthetic-no-device','--interval','0']
            first=subprocess.run(args,capture_output=True,text=True)
            self.assertEqual(first.returncode,0,first.stderr)
            rows=(td/'run/results.jsonl').read_text(encoding='utf-8').splitlines()
            self.assertEqual(len(rows),403)
            second=subprocess.run(args,capture_output=True,text=True)
            self.assertEqual(second.returncode,0,second.stderr)
            self.assertEqual((td/'run/results.jsonl').read_text(encoding='utf-8').splitlines(),rows)
            state=json.loads((td/'run/run-status.json').read_text(encoding='utf-8'))
            self.assertEqual(state['status'],'ALL_INPUTS_PROCESSED')
            self.assertEqual(state['hits'],0)
            self.assertEqual(state['unresolved'],2)


if __name__ == '__main__':
    unittest.main()
