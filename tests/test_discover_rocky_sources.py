import unittest

from scripts.discover_rocky_sources import find_latest_filename


class DiscoverRockySourcesTest(unittest.TestCase):
    def test_meta_package_does_not_match_prefixed_components(self):
        index = "\n".join(
            [
                'gcc-toolset-14-14.0-0.el8_10.src.rpm',
                'gcc-toolset-14-gcc-14.2.1-11.el8_10.src.rpm',
                'gcc-toolset-14-gdb-14.2-3.el8_10.src.rpm',
            ]
        )
        self.assertEqual(
            find_latest_filename(index, "gcc-toolset-14"),
            'gcc-toolset-14-14.0-0.el8_10.src.rpm',
        )


if __name__ == "__main__":
    unittest.main()
