import unittest

from scripts.discover_yum_repo_packages import iter_matching_packages, select_latest


PRIMARY_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<metadata xmlns="http://linux.duke.edu/metadata/common" packages="4">
  <package type="rpm">
    <name>devtoolset-8-libstdc++-devel</name>
    <arch>x86_64</arch>
    <version epoch="0" ver="8.3.1" rel="3.1.el7"/>
    <location href="Packages/d/devtoolset-8-libstdc++-devel-8.3.1-3.1.el7.x86_64.rpm"/>
  </package>
  <package type="rpm">
    <name>devtoolset-8-libstdc++-devel</name>
    <arch>x86_64</arch>
    <version epoch="0" ver="8.3.1" rel="3.2.el7"/>
    <location href="Packages/d/devtoolset-8-libstdc++-devel-8.3.1-3.2.el7.x86_64.rpm"/>
  </package>
  <package type="rpm">
    <name>devtoolset-8-libstdc++-devel</name>
    <arch>i686</arch>
    <version epoch="0" ver="8.3.1" rel="3.2.el7"/>
    <location href="Packages/d/devtoolset-8-libstdc++-devel-8.3.1-3.2.el7.i686.rpm"/>
  </package>
  <package type="rpm">
    <name>devtoolset-8-gcc</name>
    <arch>src</arch>
    <version epoch="0" ver="8.3.1" rel="3.2.el7"/>
    <location href="devtoolset-8-gcc-8.3.1-3.2.el7.src.rpm"/>
  </package>
</metadata>
"""


class DiscoverYumRepoPackagesTest(unittest.TestCase):
    def test_iter_matching_packages_filters_by_arch(self):
        entries = list(
            iter_matching_packages(
                PRIMARY_XML,
                ["devtoolset-8-libstdc++-devel"],
                arches=["x86_64"],
            )
        )
        self.assertEqual(2, len(entries))
        self.assertTrue(all(entry["arch"] == "x86_64" for entry in entries))

    def test_select_latest_prefers_higher_release(self):
        entries = list(
            iter_matching_packages(
                PRIMARY_XML,
                ["devtoolset-8-libstdc++-devel"],
                arches=["x86_64"],
            )
        )
        latest = select_latest(entries)
        self.assertEqual("8.3.1", latest["devtoolset-8-libstdc++-devel"]["version"])
        self.assertEqual("3.2.el7", latest["devtoolset-8-libstdc++-devel"]["release"])


if __name__ == "__main__":
    unittest.main()
