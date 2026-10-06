"""JD 16 visible UI collector. Run one phone worker at a time; never automate authentication."""
import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
import uiautomator2 as u2
from sales_parser import parse_display


PKG = 'com.jingdong.app.mall'


class HumanRequired(RuntimeError):
    pass


def norm(text):
    return ''.join(c for c in (text or '') if not c.isspace() and unicodedata.category(c) != 'Cf')


class Collector:
    def __init__(self, serial, evidence):
        self.d = u2.connect(serial)
        self.d.implicitly_wait(1)
        self.sdk = self.d.info['sdkInt']
        self.evidence = Path(evidence)
        self.evidence.mkdir(parents=True, exist_ok=True)

    def capture(self, name):
        before = self.d.info
        if before['currentPackageName'] != PKG:
            raise RuntimeError('JD is not in the foreground: ' + before['currentPackageName'])
        xml = self.d.dump_hierarchy()
        after = self.d.info
        if before['currentPackageName'] != after['currentPackageName']:
            raise RuntimeError('Foreground changed during capture: ' + before['currentPackageName']
                               + ' -> ' + after['currentPackageName'])
        package = after['currentPackageName']
        root = ET.fromstring(xml)
        nodes = [n for n in root.iter('node') if n.get('package') == package]
        text = '\n'.join(n.get('text', '') + n.get('content-desc', '') for n in nodes)
        if package == PKG and '京东隐私政策协议' in text:
            raise HumanRequired('JD first-use privacy selection requires user')
        if any(t in text for t in ('京东验证', '检测到安全风险', '快速验证', '拖动滑块', '安全验证')):
            raise HumanRequired('JD requires manual verification')
        if package != PKG:
            raise RuntimeError('JD is not in the foreground: ' + package)
        if any(n.get('resource-id', '').startswith('com.jd.lib.login.feature:') for n in nodes) or any(t in text for t in ('前往登录', '短信验证码', '登录注册')):
            raise HumanRequired('JD requires manual login')
        # Persist task evidence only after confirming a stable, ordinary JD page.
        # Authentication dialogs and other foreground apps are not evidence.
        # Persist only task controls, not addresses, recommendations, or account data.
        safe = ET.Element('task-evidence')
        for n in nodes:
            label = n.get('text', '')
            desc = n.get('content-desc', '')
            rid = n.get('resource-id', '')
            if (label.startswith('https://item.jd.com/') or label.startswith('全网热销')
                    or desc.startswith('自营') or rid == 'com.jd.lib.productdetail.feature:id/ale'):
                ET.SubElement(safe, 'node', {k: n.get(k, '') for k in
                              ('text', 'content-desc', 'resource-id', 'class', 'bounds')})
        (self.evidence / name).write_text(ET.tostring(safe, encoding='unicode'), encoding='utf-8')
        # Transition animations can leave displaced copies of controls in XML.
        stable_nodes = []
        for window in list(root):
            b = list(map(int, re.findall(r'-?\d+', window.get('bounds', ''))))
            if window.get('package') == package and len(b) == 4 and b[0] == 0 and b[2] == after['displayWidth']:
                stable_nodes.extend(window.iter('node'))
        visible = []
        for node in stable_nodes:
            b = list(map(int, re.findall(r'-?\d+', node.get('bounds', ''))))
            if len(b) == 4 and 0 <= b[0] < b[2] <= after['displayWidth'] and 0 <= b[1] < b[3] <= after['displayHeight']:
                visible.append(node)
        return visible

    @staticmethod
    def find(nodes, resource):
        return next((n for n in nodes if n.get('resource-id') == resource), None)

    def tap(self, node):
        if node is None:
            raise RuntimeError('Expected visible control missing')
        b = list(map(int, re.findall(r'\d+', node.get('bounds', ''))))
        self.d.click((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)

class JD16Collector(Collector):
    """Observed JD 16 full-site search and accessible product header on the phone."""

    @staticmethod
    def field(nodes):
        matches = [n for n in nodes if n.get('class') == 'android.widget.EditText']
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def submit(nodes):
        matches = [n for n in nodes if n.get('text') == '搜索'
                   and n.get('class') in ('android.widget.TextView', 'android.widget.Button')]
        if len(matches) != 1:
            raise RuntimeError('Full-site search submit is not unique')
        return matches[0]

    def collect(self, record):
        sku = record['sku']
        nodes = self.capture(f'{sku}-entry.xml')
        detail = self.find(nodes, 'com.jd.lib.productdetail.feature:id/ale')
        if detail is not None and self.field(nodes) is None:
            self.d.press('back')
            time.sleep(.7)
        field = None
        deadline = time.monotonic() + 5
        opened_home_search = False
        while time.monotonic() < deadline:
            nodes = self.capture(f'{sku}-search.xml')
            field = self.field(nodes)
            if field is not None:
                break
            home = self.find(nodes, 'com.jingdong.app.mall:id/b6o')
            if home is not None and not opened_home_search:
                self.tap(home)
                opened_home_search = True
                time.sleep(.7)
                continue
            time.sleep(.3)
        if field is None:
            raise RuntimeError('JD 16 full-site input is not ready; do not use seconds-delivery search')
        self.tap(field)
        nodes = self.capture(f'{sku}-focus.xml')
        field = self.field(nodes)
        if field is None or field.get('focused') != 'true':
            raise RuntimeError('Full-site input is not focused')
        url = f'https://item.jd.com/{sku}.html'
        # Android input text lost trailing characters in this React input; direct
        # accessible set_text was observed to preserve the full link exactly.
        self.d(className='android.widget.EditText', focused=True).set_text(url)
        nodes = self.capture(f'{sku}-input.xml')
        field = self.field(nodes)
        if field is None or field.get('text') != url:
            raise RuntimeError('Full-site URL input does not exactly match requested SKU')
        self.tap(self.submit(nodes))
        observations = []
        started = time.monotonic()
        actual_title = ''
        while time.monotonic() - started < 15:
            nodes = self.capture(f'{sku}-detail.xml')
            titles = [n for n in nodes if n.get('class') == 'android.widget.TextView'
                      and norm(n.get('text')) == norm(record['商品名称'])]
            # Require the product-detail footer and exactly one expected title;
            # never accept a recommended search result or a matching title alone.
            if len(titles) == 1 and self.find(nodes, 'com.jd.lib.productdetail.feature:id/ale') is not None:
                title = titles[0]
                actual_title = title.get('text', '').strip()
                title_box = list(map(int, re.findall(r'\d+', title.get('bounds', ''))))
                width = self.d.info['displayWidth']
                metrics = []
                for node in nodes:
                    raw = node.get('text', '')
                    box = list(map(int, re.findall(r'\d+', node.get('bounds', ''))))
                    if (node.get('class') == 'android.widget.TextView' and raw.startswith('全网热销')
                            and len(box) == 4 and len(title_box) == 4
                            and box[0] >= width * .45 and box[3] <= title_box[1]):
                        metrics.append(raw)
                if len(metrics) > 1:
                    raise RuntimeError('Product header metric is not unique')
                raw = metrics[0] if metrics else ''
                observations.append((raw, time.monotonic()))
                if (len(observations) >= 2 and observations[-2][0] == raw
                        and observations[-1][1] - observations[-2][1] >= .6
                        and (raw or time.monotonic() - started >= 3)):
                    parsed = parse_display(raw)
                    return {
                        'sku': sku, 'expected_title': record['商品名称'], 'observed_title': actual_title,
                        'raw_metric': raw or None, 'parsed': parsed,
                        'hit': None if parsed is None else parsed['hit'],
                        'status': '未显示全网热销' if not raw else ('热销字段需核验' if parsed is None else parsed['status']),
                        'collected_at': datetime.now().astimezone().isoformat(), 'navigation_url': url,
                        'identity_basis': 'JD16全站搜索完整SKU链接输入核对，唯一标题与详情按钮一致，标题上方价格区热销字段连续两次一致',
                        'evidence': str(self.evidence / f'{sku}-detail.xml'),
                        'navigation_evidence': str(self.evidence / f'{sku}-input.xml'),
                        'source_sheet': record.get('source_sheet'), 'source_excel_row': record.get('source_excel_row'),
                        'collector_profile': 'jd16', 'identity_verified': True,
                    }
            else:
                observations = []
            time.sleep(.7)
        # A real detail page can have a renamed title (for example a brand
        # prefix added after the source workbook). Keep it unknown and move on;
        # the visible metric must not be attributed to this SKU without identity.
        width = self.d.info['displayWidth']
        candidates = []
        for node in nodes:
            text = node.get('text', '')
            desc = node.get('content-desc', '')
            box = list(map(int, re.findall(r'\d+', node.get('bounds', ''))))
            if (node.get('class') == 'android.widget.TextView' and norm(text)
                    and norm(desc) == '自营' + norm(text) and len(box) == 4
                    and box[2] - box[0] >= width * .8):
                candidates.append(node)
        if len(candidates) == 1 and self.find(nodes, 'com.jd.lib.productdetail.feature:id/ale') is not None:
            observed = candidates[0].get('text', '').strip()
            return {
                'sku': sku, 'expected_title': record['商品名称'], 'observed_title': observed,
                'raw_metric': None, 'parsed': None, 'hit': None,
                'status': '商品标题不一致待核验',
                'reason': '页面名称与原表不同，未取得独立SKU编号证据，热销值未归入该SKU。',
                'collected_at': datetime.now().astimezone().isoformat(), 'navigation_url': url,
                'identity_basis': '完整SKU链接已输入核对，目标商品身份仍未确认',
                'evidence': str(self.evidence / f'{sku}-detail.xml'),
                'navigation_evidence': str(self.evidence / f'{sku}-input.xml'),
                'source_sheet': record.get('source_sheet'), 'source_excel_row': record.get('source_excel_row'),
                'collector_profile': 'jd16',
            }
        raise RuntimeError('JD 16 destination title/header not established: ' + repr(actual_title))


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def unknown(record, status, reason):
    return {'sku': record['sku'], 'expected_title': record['商品名称'],
            'observed_title': None, 'raw_metric': None, 'parsed': None,
            'hit': False if status == '用户确认排除' else None,
            'identity_verified': False, 'status': status, 'reason': reason,
            'collected_at': datetime.now().astimezone().isoformat(),
            'source_sheet': record.get('source_sheet'), 'source_excel_row': record.get('source_excel_row')}


def main():
    from prepare_input import read_source
    from result_store import bind_manifest, load_latest
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--serial', required=True)
    p.add_argument('--interval', type=float, default=4)
    p.add_argument('--sample-limit', type=int, help='Explicit test subset only; default processes the whole input')
    a = p.parse_args()
    if a.interval < 0 or (a.sample_limit is not None and a.sample_limit <= 0):
        p.error('Interval must be nonnegative and sample limit positive')
    records = read_source(a.input)
    bind_manifest(a.output_dir, records)
    output = a.output_dir / 'results.jsonl'
    state = a.output_dir / 'run-status.json'
    latest = load_latest(output, records)
    counts = Counter(norm(r['商品名称']) for r in records)
    pending = [r for r in records if r['sku'] not in latest]
    if a.sample_limit is not None:
        pending = pending[:a.sample_limit]
    # One exclusive lock prevents conflicting inputs/evidence writes by workers.
    lock = a.output_dir / '.collector.lock'
    try:
        lock_fd = lock.open('x', encoding='utf-8')
    except FileExistsError:
        p.error('Worker lock exists; check the prior process before removing a stale lock')
    collector = None
    try:
        lock_fd.write(str(__import__('os').getpid()))
        lock_fd.close()
        for index, record in enumerate(pending, 1):
            started = time.monotonic()
            try:
                if record.get('exclude_reason'):
                    result = unknown(record, '用户确认排除', record['exclude_reason'])
                elif counts[norm(record['商品名称'])] > 1:
                    result = unknown(record, '同名商品待核验', '同名标题不足以确认SKU，需要独立SKU编号证据')
                else:
                    if collector is None:
                        collector = JD16Collector(a.serial, a.output_dir / 'evidence')
                    result = collector.collect(record)
            except Exception as exc:
                status = 'HUMAN_REQUIRED' if isinstance(exc, HumanRequired) else 'NAVIGATION_ERROR'
                save_json(state, {'status': status, 'resume_sku': record['sku'], 'reason': str(exc),
                                 'checked': len(latest), 'total': len(records),
                                 'at': datetime.now().astimezone().isoformat()})
                print(json.dumps({'status': status, 'resume_sku': record['sku'], 'reason': str(exc)}, ensure_ascii=True), flush=True)
                return 2 if isinstance(exc, HumanRequired) else 3
            result['duration_seconds'] = round(time.monotonic() - started, 3)
            with output.open('a', encoding='utf-8') as f:
                f.write(json.dumps(result, ensure_ascii=False) + '\n')
                f.flush()
                __import__('os').fsync(f.fileno())
            latest[result['sku']] = result
            save_json(state, {'status': 'RUNNING', 'checked': len(latest), 'total': len(records),
                             'hits': sum(r.get('hit') is True for r in latest.values())})
            print(json.dumps({'index': index, 'sku': result['sku'], 'status': result['status'],
                              'metric': result['raw_metric'], 'hit': result['hit']}, ensure_ascii=True), flush=True)
            if index < len(pending):
                time.sleep(a.interval)
        final = {'status': 'ALL_INPUTS_PROCESSED' if len(latest) == len(records) else 'SAMPLE_COMPLETED',
                 'checked': len(latest), 'total': len(records),
                 'hits': sum(r.get('hit') is True for r in latest.values()),
                 'unresolved': sum(r.get('hit') is None for r in latest.values())}
        save_json(state, final)
        print(json.dumps(final, ensure_ascii=True), flush=True)
        return 0
    finally:
        lock_fd.close()
        lock.unlink(missing_ok=True)


if __name__ == '__main__':
    raise SystemExit(main())
