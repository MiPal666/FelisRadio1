"""Translation loading with Qt 5, animation lifecycle, and RPM resource inventory."""
from pathlib import Path
import importlib.util
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]

class ReleaseUiTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('PyQt5'), 'Qt image decoder unavailable')
    def test_supplied_artwork_and_all_launcher_icons_have_transparent_corners(self):
        from PyQt5.QtGui import QImage
        paths=[ROOT/'qml/images/felisradio1.png']
        paths += [ROOT/f'icons/{size}x{size}/harbour-felisradio1.png' for size in (86,108,128,172)]
        for path in paths:
            with self.subTest(path=path):
                image=QImage(str(path))
                self.assertFalse(image.isNull())
                for x,y in ((0,0),(image.width()-1,0),(0,image.height()-1),(image.width()-1,image.height()-1)):
                    self.assertEqual(image.pixelColor(x,y).alpha(),0)
                self.assertEqual(image.pixelColor(image.width()//2,image.height()//2).alpha(),255)

    def test_czech_catalogue_covers_every_qml_source_string(self):
        root=ET.parse(ROOT/'translations/harbour-felisradio1-cs.ts').getroot()
        entries={}
        for context in root.findall('context'):
            for message in context.findall('message'):
                text=message.find('translation')
                self.assertTrue(text.text)
                self.assertNotIn(text.get('type'),('unfinished','vanished','obsolete'))
                source=message.findtext('source')
                self.assertEqual(re.findall(r'%\d',source),re.findall(r'%\d',text.text))
                entries[(context.findtext('name'),source)]=text.text
        for path in (ROOT/'qml').rglob('*.qml'):
            for source in re.findall(r'qsTr\("((?:[^"\\]|\\.)*)"\)',path.read_text()):
                self.assertIn((path.stem,source),entries)
        self.assertEqual(root.get('sourcelanguage'),'en')
        self.assertEqual(root.get('language'),'cs_CZ')

    @unittest.skipUnless(shutil.which('lrelease6') and importlib.util.find_spec('PyQt5'), 'Qt Linguist / PyQt5 unavailable')
    def test_qt5_loads_czech_regional_fallback_and_english_default(self):
        with tempfile.TemporaryDirectory() as folder:
            compiled=Path(folder)/'harbour-felisradio1-cs.qm'
            result=subprocess.run(['lrelease6','-nounfinished',str(ROOT/'translations/harbour-felisradio1-cs.ts'),'-qm',str(compiled)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            script='''from PyQt5.QtCore import QCoreApplication,QTranslator,QLocale
import sys
app=QCoreApplication([])
translator=QTranslator()
assert translator.load(QLocale('cs_CZ'),'harbour-felisradio1','-',sys.argv[1])
app.installTranslator(translator)
assert app.translate('Backend','This phone')=='Tento telefon'
assert app.translate('MainPage','About')=='O aplikaci'
assert app.translate('Backend','Playback was interrupted. Reconnecting…')=='Přehrávání bylo přerušeno. Obnovuji…'
app.removeTranslator(translator)
assert not translator.load(QLocale('de_DE'),'harbour-felisradio1','-',sys.argv[1])
assert app.translate('Backend','This phone')=='This phone'
'''
            result=subprocess.run(['python3','-c',script,folder],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    @unittest.skipUnless(shutil.which('qmlscene-qt5'), 'Host Qt5 unavailable')
    def test_marquee_moves_only_overflow_and_resets_when_inactive(self):
        with tempfile.TemporaryDirectory() as folder:
            scene=Path(folder)/'Marquee.qml'
            scene.write_text('''import QtQuick 2.6
import "'''+(ROOT/'qml').as_uri()+'''" as App
Item {
 width:200;height:100
 App.MarqueeLabel { id: title; width:180; text:'A very long live radio track title with Czech characters: příliš žluťoučký kůň' }
 function check(value, message) { if (!value) { console.warn('ASSERTION_FAILED',message);Qt.quit(); } }
 Timer {interval:1800;running:true;onTriggered:{
   check(title.overflow>0 && title.children[0].x<0,'moving: '+title.overflow+' / '+title.children[0].x);
   title.active=false;check(title.children[0].x===0,'inactive reset');
   title.text='Radio 1';
 }}
 Timer {interval:2200;running:true;onTriggered:{
   check(title.overflow===0 && title.children[0].x>0,'short title centered: '+title.overflow+' / '+title.children[0].x);
   console.warn('MARQUEE_DONE');Qt.quit();
 }}
}
''')
            env=dict(os.environ,QT_FORCE_STDERR_LOGGING='1',QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software',QML2_IMPORT_PATH=str(ROOT/'tests/qt_stubs'))
            result=subprocess.run(['qmlscene-qt5',str(scene)],env=env,capture_output=True,text=True,timeout=5)
            log=result.stdout+result.stderr
            self.assertEqual(result.returncode,0,log)
            for marker in ('ASSERTION_FAILED','ReferenceError','TypeError','Binding loop'):
                self.assertNotIn(marker,log)
            self.assertIn('MARQUEE_DONE',log)

    def test_packaging_includes_artwork_translation_and_documentation(self):
        project=(ROOT/'harbour-felisradio1.pro').read_text()
        spec=(ROOT/'rpm/harbour-felisradio1.spec').read_text()
        self.assertIn('qml/images/felisradio1.png',project)
        self.assertIn('TRANSLATIONS += translations/harbour-felisradio1-cs.ts',project)
        self.assertIn('lrelease -nounfinished',spec)
        self.assertIn('README.en.md',spec)
        for name in ('qml/pages/MainPage.qml','qml/cover/CoverPage.qml','qml/SystemPlayer.qml'):
            self.assertIn('felisradio1.png',(ROOT/name).read_text())
        for size in (86,108,128,172):
            data=(ROOT/f'icons/{size}x{size}/harbour-felisradio1.png').read_bytes()
            self.assertEqual(int.from_bytes(data[16:20],'big'),size)
            self.assertEqual(int.from_bytes(data[20:24],'big'),size)
