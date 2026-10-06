"""Classify the displayed tier, not an exact volume or a bounded sales estimate."""
import re
from decimal import Decimal

RULE = 'display-tier-100w-inclusive-1000w-exclusive-v1'
PATTERN = re.compile(r'全网热销\s*([0-9]+(?:\.[0-9]+)?)\s*(亿|万|[wW])?\s*(?:件|台|包)?\s*([+＋]|以上)?')


def parse_display(text):
    text = (text or '').strip()
    match = PATTERN.fullmatch(text)
    if not match:
        return None
    units = {'亿': Decimal(100000000), '万': Decimal(10000), 'w': Decimal(10000), 'W': Decimal(10000)}
    value = Decimal(match[1]) * units.get(match[2], Decimal(1))
    hit = Decimal(1000000) <= value < Decimal(10000000)
    return {'raw': text, 'display_floor': str(value), 'suffix': match[3] or '',
            'open_ended': bool(match[3]), 'hit': hit, 'rule': RULE,
            'status': '命中显示档位' if hit else '展示档位未命中'}
