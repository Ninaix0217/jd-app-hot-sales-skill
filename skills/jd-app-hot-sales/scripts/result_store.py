"""Resume and reclassify only within the same normalized input manifest."""
import hashlib
import json
from pathlib import Path
from sales_parser import parse_display


def digest(records):
    return hashlib.sha256(json.dumps(records, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def classified(row):
    row = dict(row)
    # Older known-identity observations can be classified under a changed rule.
    # A title mismatch or explicit exclusion cannot become a hit from its metric.
    if row.get('identity_verified') is True:
        parsed = parse_display(row.get('raw_metric'))
        row.update(parsed=parsed, hit=None if parsed is None else parsed['hit'],
                   status='未显示全网热销' if not row.get('raw_metric') else
                   ('热销字段需核验' if parsed is None else parsed['status']))
    else:
        row.update(parsed=None, hit=False if row.get('status') == '用户确认排除' else None, raw_metric=None)
    return row


def load_latest(path, records):
    allowed = {r['sku'] for r in records}
    latest = {}
    if Path(path).exists():
        for line in Path(path).read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            if row['sku'] not in allowed:
                raise ValueError('Result contains a SKU outside this input')
            latest[row['sku']] = classified(row)
    return latest


def bind_manifest(directory, records):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'manifest.json'
    signature = digest(records)
    if path.exists():
        if json.loads(path.read_text(encoding='utf-8'))['input_sha256'] != signature:
            raise ValueError('Output directory belongs to a different input; choose a new directory')
    elif (directory / 'results.jsonl').exists():
        raise ValueError('Results without an input manifest must not be silently reused')
    else:
        path.write_text(json.dumps({'input_sha256': signature, 'records': records},
                                   ensure_ascii=False, indent=2), encoding='utf-8')
    return signature
