import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CheckLibstdcxxNonsharedBuildTests(unittest.TestCase):
    def test_invalidation_list_covers_condition_variable_overlay_outputs(self):
        script = (ROOT / "scripts/check_libstdcxx_nonshared_build.sh").read_text()

        self.assertIn('"$base/nonshared11/condition_variable.lo" \\', script)
        self.assertIn('"$base/nonshared11/condition_variable.o" \\', script)
        self.assertIn('"$base/nonshared11/cxx11-ios_failure.lo" \\', script)
        self.assertIn('"$base/nonshared11/cxx11-ios_failure.o" \\', script)

    def test_prepare_rpmbuild_tree_copies_core_specs_after_meta_specs(self):
        script = (ROOT / "scripts/prepare_rpmbuild_tree.sh").read_text()

        self.assertLess(
            script.index('copy_specs "$GENERATED_META_SPECS"'),
            script.index('copy_specs "$GENERATED_CORE_SPECS"'),
        )


if __name__ == "__main__":
    unittest.main()
