import argparse
import json
from pathlib import Path
from prepare_input import read_source
from result_store import bind_manifest, load_latest
from sales_parser import RULE


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--run-dir', type=Path, required=True)
    a = p.parse_args()
    records = read_source(a.input)
    bind_manifest(a.run_dir, records)
    latest = load_latest(a.run_dir / 'results.jsonl', records)
    rows = []
    for r in records:
        v = latest.get(r['sku'], {})
        rows.append({'sku': r['sku'], 'title': r['商品名称'],
                     'raw_metric': v.get('raw_metric'), 'display_floor': (v.get('parsed') or {}).get('display_floor'),
                     'status': v.get('status', '尚未采集'), 'hit': v.get('hit'),
                     'collected_at': v.get('collected_at'), 'source_sheet': r.get('source_sheet'),
                     'source_excel_row': r.get('source_excel_row'), 'reason': v.get('reason'),
                     'observed_title': v.get('observed_title')})
    data = {'rule': RULE, 'total': len(records), 'checked': len(latest),
            'hits': sum(r['hit'] is True for r in rows),
            'unresolved': sum(r['sku'] in latest and r['hit'] is None for r in rows),
            'pending': len(records) - len(latest), 'rows': rows}
    out = a.run_dir / 'export-data.json'
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: data[k] for k in ('total','checked','hits','unresolved','pending')}, ensure_ascii=True))


if __name__ == '__main__':
    main()
