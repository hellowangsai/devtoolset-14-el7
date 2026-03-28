import unittest
from pathlib import Path

from scripts.render_scl_specs import render
from scripts.rewrite_scl_spec import (
    rewrite_binutils,
    rewrite_gcc,
    rewrite_gdb,
    rewrite_generic,
)


ROOT = Path(__file__).resolve().parents[1]


class RenderSclSpecsTest(unittest.TestCase):
    def test_runtime_template_is_rendered(self):
        template = (ROOT / "specs" / "devtoolset-14-runtime.spec.in").read_text(
            encoding="utf-8"
        )
        rendered = render(template)
        self.assertIn("Name:           devtoolset-14-runtime", rendered)
        self.assertIn("/opt/rh/devtoolset-14/root", rendered)
        self.assertIn("/etc/scl/prefixes/devtoolset-14", rendered)


class RewriteSpecTest(unittest.TestCase):
    def test_generic_rewrite_swaps_toolset_prefixes(self):
        source = (ROOT / "tests" / "fixtures" / "gcc-toolset-14-binutils.spec").read_text(
            encoding="utf-8"
        )
        rendered = rewrite_generic(source)
        self.assertIn("Name: devtoolset-14-binutils", rendered)
        self.assertIn("/opt/rh/devtoolset-14/root/usr/bin", rendered)
        self.assertNotIn("gcc-toolset-14", rendered)

    def test_generic_rewrite_falls_back_build_ldflags_macro(self):
        rendered = rewrite_generic("LDFLAGS='%{build_ldflags}'")
        self.assertIn("LDFLAGS='%{?__global_ldflags}'", rendered)

    def test_gcc_rewrite_forces_el7_defaults(self):
        source = (ROOT / "tests" / "fixtures" / "gcc-toolset-14-gcc.spec").read_text(
            encoding="utf-8"
        )
        rendered = rewrite_gcc(source)
        self.assertIn("%global devtoolset14_el7 1", rendered)
        self.assertIn("--enable-languages=%{devtoolset14_languages}", rendered)
        self.assertIn("--disable-multilib", rendered)
        self.assertIn("%package -n devtoolset-14-libasan", rendered)
        self.assertIn("%package -n devtoolset-14-libtsan", rendered)
        self.assertIn("Patch1002: gcc14-libstdc++-compat-el7.patch", rendered)
        self.assertIn("%patch -P1002 -p0 -b .libstdc++-compat-el7~", rendered)
        self.assertNotIn("BuildRequires: /lib/libc.so.6 /usr/lib/libc.so", rendered)
        self.assertNotIn("gcc-toolset-14", rendered)

    def test_generic_rewrite_updates_bootstrap_toolset_reference(self):
        rendered = rewrite_generic("%global scl_testing_prefix gcc-toolset-13-")
        self.assertIn("%global scl_testing_prefix devtoolset-11-", rendered)

    def test_gcc_rewrite_turns_x86_64_multilib_off(self):
        rendered = rewrite_gcc(
            "\n".join(
                [
                    "%global multilib_64_archs sparc64 ppc64 ppc64p7 x86_64",
                    "#if __WORDSIZE == 32",
                    "%ifarch %{multilib_64_archs}",
                    "`cat $(find %{gcc_target_platform}/32/libstdc++-v3/include -name c++config.h)`",
                    "%else",
                    "`cat $(find %{gcc_target_platform}/libstdc++-v3/include -name c++config.h)`",
                    "%endif",
                    "#else",
                    "%ifarch %{multilib_64_archs}",
                    "`cat $(find %{gcc_target_platform}/libstdc++-v3/include -name c++config.h)`",
                    "%else",
                    "`cat $(find %{gcc_target_platform}/64/libstdc++-v3/include -name c++config.h)`",
                    "%endif",
                ]
            )
        )
        self.assertIn("%global multilib_64_archs sparc64 ppc64 ppc64p7", rendered)
        self.assertNotIn("%global multilib_64_archs sparc64 ppc64 ppc64p7 x86_64", rendered)

    def test_gcc_rewrite_creates_docdir_in_install(self):
        rendered = rewrite_gcc(
            "%install\nrm -rf %{buildroot}\nmkdir -p %{buildroot}\n"
        )
        self.assertIn(
            "%install\nrm -rf %{buildroot}\nmkdir -p %{buildroot}\nmkdir -p %{buildroot}%{_docdir}\n",
            rendered,
        )

    def test_gcc_rewrite_uses_libubsan1_runtime_name(self):
        rendered = rewrite_gcc(
            "%package -n %{?scl_prefix}libubsan-devel\nRequires: libubsan%{_isa} >= 8.3.1\n"
        )
        self.assertIn("Requires: libubsan1%{_isa} >= 8.3.1", rendered)
        self.assertNotIn("Requires: libubsan%{_isa} >= 8.3.1", rendered)

    def test_gcc_rewrite_forces_macro_toggles(self):
        rendered = rewrite_gcc(
            "\n".join(
                [
                    "%global build_libtsan 1",
                    "%global build_liblsan 1",
                    "%global build_libhwasan 1",
                    "%global build_d 1",
                    "%global build_m2 1",
                    "%global build_offload_nvptx 1",
                    "%global build_offload_amdgcn 1",
                    "%global build_libasan 0",
                    "%global build_libubsan 0",
                ]
            )
        )
        self.assertIn("%global build_libtsan 0", rendered)
        self.assertIn("%global build_liblsan 0", rendered)
        self.assertIn("%global build_libhwasan 0", rendered)
        self.assertIn("%global build_d 0", rendered)
        self.assertIn("%global build_m2 0", rendered)
        self.assertIn("%global build_offload_nvptx 0", rendered)
        self.assertIn("%global build_offload_amdgcn 0", rendered)
        self.assertIn("%global build_libasan 1", rendered)
        self.assertIn("%global build_libubsan 1", rendered)

    def test_gcc_rewrite_strips_libgccjit_sections(self):
        rendered = rewrite_gcc(
            "\n".join(
                [
                    "%package -n %{?scl_prefix}libgccjit",
                    "Summary: jit",
                    "",
                    "%description -n %{?scl_prefix}libgccjit",
                    "desc",
                    "",
                    "%package -n %{?scl_prefix}libgccjit-devel",
                    "Summary: jit-devel",
                    "",
                    "%description -n %{?scl_prefix}libgccjit-devel",
                    "desc",
                    "",
                    "%package -n %{?scl_prefix}libgccjit-docs",
                    "BuildRequires: python3-sphinx",
                    "",
                    "%description -n %{?scl_prefix}libgccjit-docs",
                    "docs",
                    "",
                    "%package -n libquadmath",
                    "Summary: quadmath",
                    "",
                    "# Build libgccjit separately, so that normal compiler binaries aren't -fpic",
                    "mkdir objlibgccjit",
                    "cd objlibgccjit",
                    "make %{?_smp_mflags} BOOT_CFLAGS=\"$OPT_FLAGS\" all-gcc",
                    "cp -a gcc/libgccjit.so* ../gcc/",
                    "cd ..",
                    "",
                    "rm -f $FULLEPATH/libgccjit.so",
                    "mkdir -p %{buildroot}%{_prefix}/%{_lib}/",
                    "cp -a objlibgccjit/gcc/libgccjit.so.* %{buildroot}%{_prefix}/%{_lib}/",
                    "rm -f $FULLPATH/libgccjit.so",
                    "echo '/* GNU ld script */",
                    "%{oformat}",
                    "INPUT ( %{_prefix}/%{_lib}/libgccjit.so.0 )' > $FULLPATH/libgccjit.so",
                    "cp -a ../gcc/jit/libgccjit*.h $FULLPATH/include/",
                    "/usr/bin/install -c -m 644 objlibgccjit/gcc/doc/libgccjit.info %{buildroot}/%{_infodir}/",
                    "gzip -9 %{buildroot}/%{_infodir}/libgccjit.info",
                    "",
                    "%post -n %{?scl_prefix}libgccjit -p /sbin/ldconfig",
                    "",
                    "%postun -n %{?scl_prefix}libgccjit -p /sbin/ldconfig",
                    "",
                    "%post -n %{?scl_prefix}libgccjit-docs",
                    "if [ -f %{_infodir}/libgccjit.info.gz ]; then",
                    "  /sbin/install-info --info-dir=%{_infodir} %{_infodir}/libgccjit.info.gz || :",
                    "fi",
                    "",
                    "%preun -n %{?scl_prefix}libgccjit-docs",
                    "if [ $1 = 0 -a -f %{_infodir}/libgccjit.info.gz ]; then",
                    "  /sbin/install-info --delete --info-dir=%{_infodir} %{_infodir}/libgccjit.info.gz || :",
                    "fi",
                    "",
                    "%post -n libquadmath",
                    "/sbin/ldconfig",
                    "",
                    "echo '/* GNU ld script */",
                    "%{oformat2}",
                    "INPUT ( %{_prefix}/lib64/libgccjit.so.0 )' > 64/libgccjit.so",
                    "echo '/* GNU ld script */",
                    "%{oformat2}",
                    "INPUT ( %{_prefix}/lib/libgccjit.so.0 )' > 32/libgccjit.so",
                    "",
                    "%files -n %{?scl_prefix}libgccjit",
                    "%{_prefix}/%{_lib}/libgccjit.so*",
                    "",
                    "%files -n %{?scl_prefix}libgccjit-devel",
                    "%{_prefix}/lib/gcc/%{gcc_target_platform}/%{gcc_major}/libgccjit.so",
                    "",
                    "%if 0",
                    "%files -n %{?scl_prefix}libgccjit-docs",
                    "%{_infodir}/libgccjit.info*",
                    "%endif",
                    "",
                    "%files plugin-devel",
                    "%{_prefix}/lib/gcc/%{gcc_target_platform}/%{gcc_major}/plugin",
                ]
            )
        )
        self.assertNotIn("%package -n %{?scl_prefix}libgccjit", rendered)
        self.assertNotIn("cp -a gcc/libgccjit.so* ../gcc/", rendered)
        self.assertNotIn("objlibgccjit/gcc/libgccjit.so.*", rendered)
        self.assertNotIn("%post -n %{?scl_prefix}libgccjit -p /sbin/ldconfig", rendered)
        self.assertNotIn("%files -n %{?scl_prefix}libgccjit", rendered)
        self.assertNotIn("INPUT ( %{_prefix}/lib64/libgccjit.so.0 )' > 64/libgccjit.so", rendered)
        self.assertNotIn("INPUT ( %{_prefix}/lib/libgccjit.so.0 )' > 32/libgccjit.so", rendered)
        self.assertNotIn("%{_prefix}/lib/gcc/%{gcc_target_platform}/%{gcc_major}/32/libgccjit.so", rendered)
        self.assertIn("%package -n libquadmath", rendered)
        self.assertIn("%post -n libquadmath", rendered)
        self.assertIn("%files plugin-devel", rendered)

    def test_binutils_rewrite_enables_bootstrap_defaults(self):
        rendered = rewrite_binutils(
            "\n".join(
                [
                    "%bcond_with bootstrap",
                    "%bcond_without gold",
                    "%bcond_without debuginfod",
                    "%define bootstrapping 0",
                    "%define gcc_package gcc",
                    "%define gxx_package gcc-c++",
                    "%define gcc_for_binutils /usr/bin/gcc",
                    "%define gxx_for_binutils /usr/bin/g++",
                    "BuildRequires: gcc-c++",
                    "\trm -f $local_mandir/{dlltool,nlmconv,windres,windmc}*",
                    "Name: gcc-toolset-14-binutils",
                ]
            )
        )
        self.assertIn("%bcond_without bootstrap", rendered)
        self.assertIn("%bcond_with gold", rendered)
        self.assertIn("%bcond_with debuginfod", rendered)
        self.assertIn("%define bootstrapping 1", rendered)
        self.assertIn("%define gcc_package devtoolset-11-gcc", rendered)
        self.assertIn("%define gxx_package devtoolset-11-gcc-c++", rendered)
        self.assertIn(
            "%define gcc_for_binutils /opt/rh/devtoolset-11/root/usr/bin/gcc",
            rendered,
        )
        self.assertIn(
            "%define gxx_for_binutils /opt/rh/devtoolset-11/root/usr/bin/g++",
            rendered,
        )
        self.assertIn("BuildRequires: devtoolset-11-gcc-c++", rendered)
        self.assertIn("\trm -f $local_infodir/{ctf-spec,sframe-spec}.info*", rendered)
        self.assertIn("Name: devtoolset-14-binutils", rendered)

    def test_gdb_rewrite_uses_bootstrap_compiler_and_disables_optional_features(self):
        rendered = rewrite_gdb(
            "\n".join(
                [
                    "%global _python_bytecompile_extra 0",
                    "BuildRequires: %{?scl_prefix}gcc-c++",
                    "BuildRequires: expat-devel%{buildisa}",
                    "BuildRequires: cmake",
                    "BuildRequires: source-highlight-devel",
                    "BuildRequires: boost-devel",
                    "BuildRequires: elfutils-debuginfod-client-devel",
                    "BuildRequires: texinfo-tex",
                    "BuildRequires: texlive-collection-latexrecommended",
                    "%global have_libipt 1",
                    "%global have_debuginfod 1",
                    "%global use_scl_for_debuginfod 1",
                    "This package provides INFO, HTML and PDF user manual for GDB.",
                    "%doc %{gdb_build}/gdb/doc/{gdb,annotate}.{html,pdf}",
                    "# Populate CFLAGS, LDFLAGS, CC, CXX, etc.",
                    "%set_build_flags",
                    'cd %{gdb_build}$fprofile',
                    '',
                    'export CFLAGS="$RPM_OPT_FLAGS %{?_with_asan:-fsanitize=address}"',
                    'GDB_FULL_CONFIGURE_FLAGS="\\',
                    '\t--with-expat \\',
                    '\t--enable-unit-tests"',
                    "%make_build \\",
                    "     -C gdb/doc {gdb,annotate}{.info,/index.html,.pdf} MAKEHTMLFLAGS=--no-split MAKEINFOFLAGS=--no-split V=1",
                    "Name: gcc-toolset-14-gdb",
                ]
            )
        )
        self.assertIn("%global _without_python 1", rendered)
        self.assertIn("BuildRequires: devtoolset-11-gcc-c++", rendered)
        self.assertNotIn("BuildRequires: expat-devel%{buildisa}", rendered)
        self.assertNotIn("BuildRequires: cmake", rendered)
        self.assertNotIn("BuildRequires: source-highlight-devel", rendered)
        self.assertNotIn("BuildRequires: boost-devel", rendered)
        self.assertNotIn("BuildRequires: elfutils-debuginfod-client-devel", rendered)
        self.assertNotIn("BuildRequires: texinfo-tex", rendered)
        self.assertNotIn("BuildRequires: texlive-collection-latexrecommended", rendered)
        self.assertIn("%global have_libipt 0", rendered)
        self.assertIn("%global have_debuginfod 0", rendered)
        self.assertIn("%global use_scl_for_debuginfod 0", rendered)
        self.assertIn("--without-expat", rendered)
        self.assertIn("--disable-source-highlight", rendered)
        self.assertIn("export CC=/opt/rh/devtoolset-11/root/usr/bin/gcc", rendered)
        self.assertIn("export CXX=/opt/rh/devtoolset-11/root/usr/bin/g++", rendered)
        self.assertIn("export RANLIB=/opt/rh/devtoolset-11/root/usr/bin/gcc-ranlib", rendered)
        self.assertIn("This package provides the INFO user manual for GDB.", rendered)
        self.assertNotIn("{gdb,annotate}.{html,pdf}", rendered)
        self.assertIn(
            "%make_build \\\n     -C gdb/doc {gdb,annotate}.info MAKEINFOFLAGS=--no-split V=1",
            rendered,
        )
        self.assertIn("Name: devtoolset-14-gdb", rendered)


if __name__ == "__main__":
    unittest.main()
