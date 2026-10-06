from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS=Path(__file__).resolve().parents[1]/'skills/jd-app-hot-sales/scripts'
sys.path.insert(0,str(SCRIPTS))
from collect import Collector, HumanRequired
import collect


class FakeDevice:
    def __init__(self, xml, after='com.jingdong.app.mall'):
        self.xml=xml
        self.after=after
        self.read=False

    @property
    def info(self):
        return {'currentPackageName':self.after if self.read else 'com.jingdong.app.mall',
                'displayWidth':1080,'displayHeight':2376}

    def dump_hierarchy(self):
        self.read=True
        return self.xml


def xml(text, rid=''):
    return ('<hierarchy><node package="com.jingdong.app.mall" bounds="[0,0][1080,2376]">'
            f'<node package="com.jingdong.app.mall" text="{text}" resource-id="{rid}" bounds="[10,10][800,100]"/>'
            '</node></hierarchy>')


class EvidenceTests(unittest.TestCase):
    def test_runtime_symbols_available(self):
        self.assertTrue(callable(collect.u2.connect))
        self.assertIs(collect.parse_display('全网热销100万+')['hit'], True)

    def collector(self, td, device):
        c=Collector.__new__(Collector)
        c.d=device
        c.evidence=Path(td)
        return c

    def test_authentication_never_persisted(self):
        for text,rid in [('快速验证',''),('登录','com.jd.lib.login.feature:id/test'),('京东隐私政策协议','')]:
            with tempfile.TemporaryDirectory() as td:
                c=self.collector(td,FakeDevice(xml(text,rid)))
                with self.assertRaises(HumanRequired):
                    c.capture('e.xml')
                self.assertEqual(list(Path(td).iterdir()),[])

    def test_foreground_change_never_persisted(self):
        with tempfile.TemporaryDirectory() as td:
            c=self.collector(td,FakeDevice(xml('全网热销200万+'),after='other.app'))
            with self.assertRaises(RuntimeError):
                c.capture('e.xml')
            self.assertEqual(list(Path(td).iterdir()),[])

    def test_unrelated_personal_text_removed(self):
        with tempfile.TemporaryDirectory() as td:
            c=self.collector(td,FakeDevice(xml('SYNTHETIC PRIVATE ADDRESS')))
            c.capture('e.xml')
            self.assertNotIn('PRIVATE', (Path(td)/'e.xml').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
