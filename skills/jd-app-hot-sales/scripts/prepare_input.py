"""Read one explicit sheet/table. Preserve names, deduplicate SKU identifiers."""
import argparse
import csv
import json
from pathlib import Path
import re


def normalize(rows):
    records = []
    seen = {}
    for row in rows:
        raw = row.get('sku', row.get('SKU'))
        if raw is None or str(raw).strip() == '':
            continue
        if isinstance(raw, float):
            raise ValueError('SKU must be text or integer, not floating point')
        sku = str(raw).strip()
        title = str(row.get('商品名称', row.get('title', '')) or '').strip()
        if not re.fullmatch(r'[0-9]+', sku) or not title:
            raise ValueError('Every record requires a digit-only SKU and a nonempty title')
        if sku in seen:
            if title != seen[sku]['商品名称'] or row.get('exclude_reason') != seen[sku].get('exclude_reason'):
                raise ValueError('Conflicting records for SKU ' + sku)
            continue
        record = {**row, 'sku': sku, '商品名称': title}
        seen[sku] = record
        records.append(record)
    if not records:
        raise ValueError('Input contains no records')
    return records


def read_source(path, sheet=None, header_row=1):
    path = Path(path)
    if path.suffix.lower() == '.json':
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        rows = data['records'] if isinstance(data, dict) else data
    elif path.suffix.lower() == '.csv':
        with path.open(encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))
    elif path.suffix.lower() == '.xlsx':
        import openpyxl  # Reading only; XLSX authoring uses the Artifact Tool exporter.
        if not sheet:
            raise ValueError('XLSX requires an explicit --sheet; never merge sheets implicitly')
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            ws = wb[sheet]
            values = list(ws.iter_rows(min_row=header_row, values_only=True))
            headers = [str(x).strip() if x is not None else '' for x in values[0]]
            if not any(h in ('sku', 'SKU') for h in headers) or not any(h in ('title', '商品名称') for h in headers):
                raise ValueError('Header requires SKU/sku and 商品名称/title columns')
            rows = [{**dict(zip(headers, v)), 'source_sheet': sheet,
                     'source_excel_row': n} for n, v in enumerate(values[1:], header_row + 1)]
        finally:
            wb.close()
    else:
        raise ValueError('Supported inputs: JSON, CSV, XLSX')
    return normalize(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--sheet')
    p.add_argument('--header-row', type=int, default=1)
    a = p.parse_args()
    if a.header_row < 1:
        p.error('--header-row must be positive')
    records = read_source(a.source, a.sheet, a.header_row)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps({'records': records}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'records': len(records), 'output': str(a.output)}, ensure_ascii=True))


if __name__ == '__main__':
    main()
