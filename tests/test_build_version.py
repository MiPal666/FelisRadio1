"""Generate the real version template with qmake and compile its C++ literals."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
QMAKE=next((path for name in ('qmake-qt5','qmake6','qmake') if (path:=shutil.which(name))),None)
CXX=shutil.which('c++')

@unittest.skipUnless(QMAKE, 'Host qmake is unavailable')
class BuildVersionTests(unittest.TestCase):
    def generate(self, folder, version):
        source=(ROOT/'harbour-felisradio1.pro').read_text()
        block=source[source.index('isEmpty(FELISRADIO1_VERSION)'):source.index('TRANSLATIONS +=')]
        (folder/'src').mkdir()
        shutil.copy2(ROOT/'src/felisradio1_version.h.in',folder/'src/felisradio1_version.h.in')
        project=folder/'check.pro'
        project.write_text('TEMPLATE = aux\nCONFIG -= qt\n'+block)
        result=subprocess.run([QMAKE,str(project),'FELISRADIO1_VERSION='+version],cwd=folder,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        header=(folder/'felisradio1_version.h').read_text()
        self.assertIn('#define FELISRADIO1_BUILD_VERSION "'+version+'"',header)
        self.assertNotIn('@',header)
        return folder/'felisradio1_version.h'

    def test_version_template_expands_rpm_value_and_retains_quotes(self):
        for version in ('0.1.0-19','9.8.7-42'):
            with self.subTest(version=version),tempfile.TemporaryDirectory() as folder:
                self.generate(Path(folder),version)

    @unittest.skipUnless(CXX, 'Host C++ compiler is unavailable')
    def test_generated_macro_compiles_as_string_and_qstringliteral_input(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);self.generate(folder,'0.1.0-19')
            source=folder/'check.cpp'
            source.write_text('''#include "felisradio1_version.h"
constexpr char version[] = FELISRADIO1_BUILD_VERSION;
// QStringLiteral also concatenates the expanded macro with a UTF-16 literal.
constexpr char16_t qtVersion[] = u"" FELISRADIO1_BUILD_VERSION;
static_assert(sizeof(version) == 9, "Wrong version string");
static_assert(sizeof(qtVersion)/sizeof(char16_t) == 9, "Wrong Qt string");
''')
            result=subprocess.run([CXX,'-std=c++11','-fsyntax-only',str(source)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
