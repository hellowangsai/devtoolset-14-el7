import tempfile
import unittest
from pathlib import Path

from scripts.analyze_libstdcxx_nonshared import read_patch_summary


class NonsharedAnalyzerTest(unittest.TestCase):
    def test_patch_summary_finds_variants_and_subdirs(self):
        with tempfile.TemporaryDirectory() as tempdir:
            patch_path = Path(tempdir) / "nonshared.patch"
            patch_path.write_text(
                "\n".join(
                    [
                        "+++ libstdc++-v3/src/nonshared98/foo.cc",
                        "+++ libstdc++-v3/src/nonshared11/bar.cc",
                        "+libstdc++_nonshared48.la",
                        "+libstdc++_nonshared80.la",
                        "+$(top_builddir)/src/nonshared98/libnonshared98convenience48.la",
                    ]
                ),
                encoding="utf-8",
            )
            summary = read_patch_summary(patch_path)
        self.assertEqual([48, 80], summary["baseline_variants"])
        self.assertEqual(["nonshared11", "nonshared98"], summary["nonshared_subdirs"])
        self.assertIn("foo.cc", summary["patched_objects"])


if __name__ == "__main__":
    unittest.main()
