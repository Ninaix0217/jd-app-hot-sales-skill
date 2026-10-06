"""Explicitly migrate local legacy observations; never imply a new live capture."""
import argparse
import json
from pathlib import Path
import unicodedata
from prepare_input import read_source
from result_store import bind_manifest, classified


def norm(text):
    return ''.join(c for c in (text or '') if not c.isspace() and unicodedata.category(c) != 'Cf')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--legacy-results',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args()
    records=read_source(a.input)
    by_sku={r['sku']:r for r in records}
    bind_manifest(a.output_dir,records)
    output=a.output_dir/'results.jsonl'
    if output.exists():
        raise ValueError('Migration requires a new output directory without results')
    latest={}
    for line in a.legacy_results.read_text(encoding='utf-8').splitlines():
        r=json.loads(line)
        if r['sku'] not in by_sku:
            raise ValueError('Legacy result outside authorized input')
        if r.get('status')!='采集失败待核验':
            latest[r['sku']]=r
    rows=[]
    for sku,v in latest.items():
        source=by_sku[sku]
        r=dict(v)
        verified=norm(v.get('expected_title'))==norm(source['商品名称']) and norm(v.get('observed_title'))==norm(source['商品名称'])
        if source.get('exclude_reason'):
            r.update(identity_verified=False,status='用户确认排除',reason=source['exclude_reason'])
        else:
            r['identity_verified']=verified
            if not verified:
                r.update(status='商品标题不一致待核验',reason='历史页面标题与此输入不同，未重新实时核验')
        r['migration_basis']='历史采集观察按当前展示档位重新分类，非本次实时采集'
        rows.append(classified(r))
    output.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    print(json.dumps({'migrated':len(rows),'hits':sum(r['hit'] is True for r in rows)},ensure_ascii=True))


if __name__=='__main__':
    main()
