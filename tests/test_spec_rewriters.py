import unittest
from pathlib import Path

from scripts.render_scl_specs import render
from scripts.rewrite_scl_spec import (
    rewrite_annobin,
    rewrite_binutils,
    rewrite_elfutils,
    rewrite_gcc,
    rewrite_gdb,
    rewrite_generic,
    rewrite_make,
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

    def test_gcc_rewrite_sets_gcc4_compatible_default_libstdcxx_abi(self):
        rendered = rewrite_gcc(
            'CONFIGURE_OPTS="\\\n'
            '\t--enable-shared --enable-threads=posix --enable-checking=release \\\n'
            '"\n'
        )
        self.assertIn("--with-default-libstdcxx-abi=gcc4-compatible", rendered)

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

    def test_gcc_rewrite_strips_32bit_libgcc_s_install_bits(self):
        rendered = rewrite_gcc(
            "\n".join(
                [
                    "%ifarch %{multilib_64_archs}",
                    "ln -sf /lib/libgcc_s.so.1 $FULLPATH/32/libgcc_s.so",
                    "%endif",
                    "",
                    "%ifarch %{multilib_64_archs}",
                    "rm -f $FULLPATH/32/libgcc_s.so",
                    "echo '/* GNU ld script",
                    "   Use the shared library, but some functions are only in",
                    "   the static library, so try that secondarily.  */",
                    "%{oformat2}",
                    "GROUP ( /lib/libgcc_s.so.1 libgcc.a )' > $FULLPATH/32/libgcc_s.so",
                    "%endif",
                    "",
                    "%{_prefix}/lib/gcc/%{gcc_target_platform}/%{gcc_major}/32/libgcc_s.so",
                ]
            )
            + "\n"
        )
        self.assertNotIn("$FULLPATH/32/libgcc_s.so", rendered)
        self.assertNotIn("%{_prefix}/lib/gcc/%{gcc_target_platform}/%{gcc_major}/32/libgcc_s.so", rendered)

    def test_gcc_rewrite_keeps_target_prefixed_gcc_binutils_wrappers(self):
        rendered = rewrite_gcc(
            "%files\n"
            "%{_prefix}/bin/gcc-ar\n"
            "%{_prefix}/bin/gcc-nm\n"
            "%{_prefix}/bin/gcc-ranlib\n"
        )
        self.assertIn("%{_prefix}/bin/%{gcc_target_platform}-gcc-ar", rendered)
        self.assertIn("%{_prefix}/bin/%{gcc_target_platform}-gcc-nm", rendered)
        self.assertIn("%{_prefix}/bin/%{gcc_target_platform}-gcc-ranlib", rendered)

    def test_gcc_rewrite_enables_gdb_plugin_files(self):
        rendered = rewrite_gcc(
            "%if 0\n"
            "%files gdb-plugin\n"
            "%{_prefix}/%{_lib}/libcc1.so*\n"
            "%endif\n"
            "\n"
            "%if %{build_offload_nvptx}\n"
            "%files -n %{?scl_prefix}offload-nvptx\n"
        )
        self.assertIn("%files gdb-plugin", rendered)
        self.assertNotIn("%if 0\n%files gdb-plugin", rendered)
        self.assertIn("%files -n %{?scl_prefix}offload-nvptx", rendered)

    def test_gcc_rewrite_removes_disabled_hwasan_artifacts(self):
        rendered = rewrite_gcc(
            "rm -f %{buildroot}%{_prefix}/%{_lib}/libssp*\n"
            "rm -f %{buildroot}%{_prefix}/%{_lib}/libvtv* || :\n"
        )
        self.assertIn("rm -f %{buildroot}%{_prefix}/%{_lib}/libhwasan* || :", rendered)
        self.assertIn("rm -f $FULLPATH/libhwasan* || :", rendered)
        self.assertIn("rm -f %{buildroot}%{_prefix}/%{_lib}/libgcc_s.so || :", rendered)
        self.assertIn("%{buildroot}%{_infodir}/libgomp.info*", rendered)
        self.assertIn("%{buildroot}%{_mandir}/man7/fsf-funding.7*", rendered)
        self.assertIn("%{buildroot}%{_prefix}/lib/gcc/%{gcc_target_platform}/%{gcc_major}/include/ssp", rendered)
        self.assertIn("%{buildroot}%{_prefix}/libexec/getconf/default", rendered)
        self.assertIn("%{buildroot}%{_root_prefix}/%{_lib}/libitm.so.1*", rendered)
        self.assertIn("%{buildroot}%{_root_prefix}/%{_lib}/libatomic.so.1*", rendered)
        self.assertIn("find %{buildroot}%{_prefix}/share/gcc-%{gcc_major}/python %{buildroot}%{_datadir}/gdb/auto-load/%{_prefix}/%{_lib} -name __pycache__", rendered)
        self.assertIn("rm -rf %{buildroot}%{_prefix}/share/locale || :", rendered)

    def test_gcc_rewrite_packages_include_fixed_and_install_tools(self):
        rendered = rewrite_gcc(
            "%{_prefix}/libexec/gcc/%{gcc_target_platform}/%{gcc_major}/cc1\n"
            "%{_prefix}/libexec/gcc/%{gcc_target_platform}/%{gcc_major}/collect2\n"
        )
        self.assertIn("%{_prefix}/lib/gcc/%{gcc_target_platform}/%{gcc_major}/include-fixed", rendered)
        self.assertIn("%{_prefix}/lib/gcc/%{gcc_target_platform}/%{gcc_major}/install-tools", rendered)
        self.assertIn("%{_prefix}/libexec/gcc/%{gcc_target_platform}/%{gcc_major}/install-tools", rendered)

    def test_gcc_rewrite_packages_libstdcxx_pretty_printers(self):
        rendered = rewrite_gcc(
            "%doc rpm.doc/changelogs/libstdc++-v3/ChangeLog* libstdc++-v3/README*\n"
        )
        self.assertIn("%{_datadir}/gcc-%{gcc_major}/python/libstdcxx", rendered)
        self.assertIn("%{_datadir}/gdb/auto-load/%{_prefix}/%{_lib}/libstdc++*gdb.py*", rendered)
        self.assertIn("%{_datadir}/gdb/auto-load/%{_prefix}/%{_lib}/__pycache__/libstdc++*gdb*.pyc", rendered)

    def test_gcc_rewrite_cleans_python_bytecode_caches_after_pretty_printers(self):
        rendered = rewrite_gcc(
            "for f in `find %{buildroot}%{_prefix}/share/gcc-%{gcc_major}/python/ \\\n"
            "\t       %{buildroot}%{_datadir}/gdb/auto-load/%{_prefix}/%{_lib}/ -name \\*.py`; do\n"
            "  r=${f/$RPM_BUILD_ROOT/}\n"
            "  %{__python3} -c 'import py_compile; py_compile.compile(\"'$f'\", dfile=\"'$r'\")'\n"
            "  %{__python3} -O -c 'import py_compile; py_compile.compile(\"'$f'\", dfile=\"'$r'\")'\n"
            "done\n\n"
        )
        self.assertIn(
            "find %{buildroot}%{_prefix}/share/gcc-%{gcc_major}/python %{buildroot}%{_datadir}/gdb/auto-load/%{_prefix}/%{_lib} -name __pycache__",
            rendered,
        )

    def test_gcc_rewrite_does_not_add_libitm_or_libatomic_runtime_packages(self):
        rendered = rewrite_gcc(
            "%if %{build_libitm}\n"
            "%files -n %{?scl_prefix}libitm-devel\n"
            "%{_prefix}/lib/gcc/%{gcc_target_platform}/%{gcc_major}/libitm.so\n"
            "%endif\n\n"
            "%if %{build_libatomic}\n"
            "%files -n %{?scl_prefix}libatomic-devel\n"
            "%{_prefix}/lib/gcc/%{gcc_target_platform}/%{gcc_major}/libatomic.so\n"
            "%endif\n"
        )
        self.assertIn("%files -n %{?scl_prefix}libitm-devel", rendered)
        self.assertIn("%files -n %{?scl_prefix}libatomic-devel", rendered)
        self.assertNotIn("%files -n libitm", rendered)
        self.assertNotIn("%files -n libatomic", rendered)
        self.assertNotIn("%{?scl:%{_root_prefix}}%{!?scl:%{_prefix}}/%{_lib}/libitm.so.1*", rendered)
        self.assertNotIn("%{?scl:%{_root_prefix}}%{!?scl:%{_prefix}}/%{_lib}/libatomic.so.1*", rendered)

    def test_gcc_rewrite_restores_libcc1_changelog_collection(self):
        rendered = rewrite_gcc(
            "mkdir -p rpm.doc/changelogs/{gcc/cp,gcc/jit,libstdc++-v3,libgomp,libatomic,libsanitizer}\n\n"
            "for i in {gcc,gcc/cp,gcc/jit,libstdc++-v3,libgomp,libatomic,libsanitizer}/ChangeLog*; do\n"
            "\tcp -p $i rpm.doc/changelogs/$i\n"
            "done\n"
        )
        self.assertIn("rpm.doc/changelogs/{gcc/cp,gcc/jit,libstdc++-v3,libgomp,libcc1,libatomic,libsanitizer}", rendered)
        self.assertIn("{gcc,gcc/cp,gcc/jit,libstdc++-v3,libgomp,libcc1,libatomic,libsanitizer}/ChangeLog*", rendered)

    def test_gcc_rewrite_relinks_libcc1_against_nonshared_libstdcxx(self):
        rendered = rewrite_gcc(
            "%ifarch sparc sparcv9 sparc64\n"
            "make %{?_smp_mflags} BOOT_CFLAGS=\"$OPT_FLAGS\" LDFLAGS_FOR_TARGET=-Wl,-z,relro,-z,now bootstrap\n"
            "%else\n"
            "make %{?_smp_mflags} BOOT_CFLAGS=\"$OPT_FLAGS\" LDFLAGS_FOR_TARGET=-Wl,-z,relro,-z,now profiledbootstrap\n"
            "%endif\n\n"
            "# Test the nonshared bits.\n"
        )
        self.assertIn("libstdc++_system.so", rendered)
        self.assertIn("sed -i -e '/^postdeps/s/-lstdc++/-lstdc++_system/' libcc1/libtool", rendered)
        self.assertIn("make -C libcc1 libcc1.la", rendered)
        self.assertLess(
            rendered.index("make -C libcc1 libcc1.la"),
            rendered.index("# Test the nonshared bits."),
        )

    def test_gcc_rewrite_sets_el7_gfortran_runtime_requirement(self):
        rendered = rewrite_gcc(
            "%package gfortran\n"
            "Summary: Fortran support for GCC %{gcc_major}\n"
            "Requires: %{?scl_prefix}gcc%{!?scl:13} = %{version}-%{release}\n"
            "Requires: libgfortran >= 8.1.1\n\n"
        )
        self.assertIn("Requires: libgfortran5 >= 8.1.1", rendered)
        self.assertNotIn("%package -n libgfortran5", rendered)

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
                    "%ldconfig_post",
                    "%ldconfig_postun",
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
        self.assertIn("/sbin/ldconfig", rendered)
        self.assertNotIn("%ldconfig_post", rendered)
        self.assertNotIn("%ldconfig_postun", rendered)
        self.assertIn("Name: devtoolset-14-binutils", rendered)

    def test_gdb_rewrite_uses_bootstrap_compiler_and_disables_optional_features(self):
        rendered = rewrite_gdb(
            "\n".join(
                [
                    "%global _python_bytecompile_extra 0",
                    "BuildRequires: %{?scl_prefix}gcc-c++",
                    "BuildRequires: libbabeltrace-devel%{buildisa}",
                    "BuildRequires: expat-devel%{buildisa}",
                    "BuildRequires: cmake",
                    "BuildRequires: source-highlight-devel",
                    "BuildRequires: boost-devel",
                    "BuildRequires: elfutils-debuginfod-client-devel",
                    "BuildRequires: texinfo-tex",
                    "BuildRequires: texlive-collection-latexrecommended",
                    "%global have_libipt 0",
                    "%global have_debuginfod 1",
                    "%global use_scl_for_debuginfod 1",
                    "This package provides INFO, HTML and PDF user manual for GDB.",
                    "%doc %{gdb_build}/gdb/doc/{gdb,annotate}.{html,pdf}",
                    "# Populate CFLAGS, LDFLAGS, CC, CXX, etc.",
                    "%set_build_flags",
                    'cd %{gdb_build}$fprofile',
                    '',
                    'export CFLAGS="$RPM_OPT_FLAGS %{?_with_asan:-fsanitize=address}"',
                    "%if 0%{have_libipt} && 0%{?el7:1} && 0%{?scl:1}",
                    "(",
                    " mkdir libipt-%{libipt_version}-root",
                    " mkdir libipt-%{libipt_version}-build",
                    " cd    libipt-%{libipt_version}-build",
                    " # -DPTUNIT:BOOL=ON has no effect on ctest.",
                    " %cmake -DCMAKE_BUILD_TYPE=RelWithDebInfo \\",
                    "\t-DPTUNIT:BOOL=OFF \\",
                    "\t-DDEVBUILD:BOOL=ON \\",
                    "\t-DBUILD_SHARED_LIBS=OFF \\",
                    "\t../../libipt-%{libipt_version}",
                    " make VERBOSE=1 %{?_smp_mflags}",
                    " ctest -V %{?_smp_mflags}",
                    " make install DESTDIR=../libipt-%{libipt_version}-root",
                    "%endif",
                    'GDB_FULL_CONFIGURE_FLAGS="\\',
                    '%if 0%{!?rhel:1} || 0%{?rhel} > 7',
                    '\t--with-babeltrace \\',
                    '%else',
                    '\t--without-babeltrace \\',
                    '%endif',
                    '\t--with-expat \\',
                    '%if %{have_libipt}',
                    '\t--with-intel-pt \\',
                    '%else',
                    '\t--without-intel-pt \\',
                    '%endif',
                    '\t--enable-unit-tests"',
                    "%make_build \\",
                    "     -C gdb/doc {gdb,annotate}{.info,/index.html,.pdf} MAKEHTMLFLAGS=--no-split MAKEINFOFLAGS=--no-split V=1",
                    "Name: gcc-toolset-14-gdb",
                ]
            )
        )
        self.assertNotIn("%global _without_python 1", rendered)
        self.assertIn("BuildRequires: devtoolset-11-gcc-c++", rendered)
        self.assertNotIn("BuildRequires: libbabeltrace-devel%{buildisa}", rendered)
        self.assertIn("BuildRequires: expat-devel%{buildisa}", rendered)
        self.assertIn("BuildRequires: cmake", rendered)
        self.assertNotIn("BuildRequires: source-highlight-devel", rendered)
        self.assertNotIn("BuildRequires: boost-devel", rendered)
        self.assertNotIn("BuildRequires: elfutils-debuginfod-client-devel", rendered)
        self.assertNotIn("BuildRequires: texinfo-tex", rendered)
        self.assertNotIn("BuildRequires: texlive-collection-latexrecommended", rendered)
        self.assertIn("%global have_libipt 1", rendered)
        self.assertIn("%global have_debuginfod 0", rendered)
        self.assertIn("%global use_scl_for_debuginfod 0", rendered)
        self.assertIn("--without-babeltrace", rendered)
        self.assertIn("--with-expat", rendered)
        self.assertIn("--with-intel-pt", rendered)
        self.assertIn("--disable-source-highlight", rendered)
        self.assertIn("export CC=/opt/rh/devtoolset-11/root/usr/bin/gcc", rendered)
        self.assertIn("export CXX=/opt/rh/devtoolset-11/root/usr/bin/g++", rendered)
        self.assertIn("export RANLIB=/opt/rh/devtoolset-11/root/usr/bin/gcc-ranlib", rendered)
        self.assertIn("CMAKE_BIN=$(command -v cmake || command -v cmake3)", rendered)
        self.assertIn("CTEST_BIN=$(command -v ctest || command -v ctest3)", rendered)
        self.assertIn("\"$CMAKE_BIN\" -DCMAKE_BUILD_TYPE=RelWithDebInfo", rendered)
        self.assertIn("\"$CTEST_BIN\" -V %{?_smp_mflags}", rendered)
        self.assertIn("This package provides the INFO user manual for GDB.", rendered)
        self.assertNotIn("{gdb,annotate}.{html,pdf}", rendered)
        self.assertIn(
            "%make_build \\\n     -C gdb/doc {gdb,annotate}.info MAKEINFOFLAGS=--no-split V=1",
            rendered,
        )
        self.assertIn("Name: devtoolset-14-gdb", rendered)

    def test_gdb_rewrite_uses_python3_for_el7_python_support(self):
        rendered = rewrite_gdb(
            "\n".join(
                [
                    "%global _python_bytecompile_extra 0",
                    "%if 0%{?rhel:1} && 0%{?rhel} <= 7",
                    "BuildRequires: python-devel%{buildisa}",
                    "%global __python /usr/bin/python2",
                    "%else",
                    "%global __python %{__python3}",
                    "BuildRequires: python3-devel%{buildisa}",
                    "%endif",
                    "%if 0%{!?_without_python:1}",
                    "\t--with-python=%{__python} \\",
                    "%else",
                    "\t--without-python \\",
                    "%endif",
                ]
            )
        )
        self.assertNotIn("BuildRequires: python-devel%{buildisa}", rendered)
        self.assertIn("BuildRequires: python3-devel%{buildisa}", rendered)
        self.assertNotIn("%global __python /usr/bin/python2", rendered)
        self.assertIn("%global __python %{__python3}", rendered)
        self.assertIn("%global __os_install_post %{expand:", rendered)
        self.assertIn("/usr/lib/rpm/brp-scl-python-bytecompile %{__python3}", rendered)
        self.assertIn("--with-python=%{__python}", rendered)

    def test_gdb_rewrite_uses_python3_for_scl_bytecompile(self):
        rendered = rewrite_gdb(
            "\n".join(
                [
                    "%global _python_bytecompile_extra 0",
                ]
            )
        )
        self.assertIn("%global __os_install_post %{expand:", rendered)
        self.assertIn("/usr/lib/rpm/brp-scl-python-bytecompile %{__python3}", rendered)

    def test_gdb_rewrite_removes_system_gdbinit_tree_recursively(self):
        rendered = rewrite_gdb(
            "rm -f $RPM_BUILD_ROOT%{_datadir}/gdb/system-gdbinit/elinos.py\n"
            "rm -f $RPM_BUILD_ROOT%{_datadir}/gdb/system-gdbinit/wrs-linux.py\n"
            "rmdir $RPM_BUILD_ROOT%{_datadir}/gdb/system-gdbinit\n"
        )
        self.assertIn("rm -rf $RPM_BUILD_ROOT%{_datadir}/gdb/system-gdbinit", rendered)
        self.assertNotIn("rmdir $RPM_BUILD_ROOT%{_datadir}/gdb/system-gdbinit", rendered)

    def test_gdb_rewrite_drops_dap_python_tree_for_el7(self):
        rendered = rewrite_gdb(
            'for i in `find $RPM_BUILD_ROOT%{_datadir}/gdb -name "*.py"`; do\n'
            "  touch -r $RPM_BUILD_DIR/%{gdb_src}/gdb/version.in $i\n"
            "done\n"
        )
        self.assertIn("rm -rf $RPM_BUILD_ROOT%{_datadir}/gdb/python/gdb/dap", rendered)

    def test_annobin_rewrite_follows_dts11_bootstrap_model(self):
        rendered = rewrite_annobin(
            "\n".join(
                [
                    "%{?scl:%scl_package annobin}",
                    "%bcond_without clangplugin",
                    "%bcond_without llvmplugin",
                    "%bcond_without plugin_rebuild",
                    "# %%if %%{without plugin_rebuild}",
                    "# %%undefine _annotated_build",
                    "# %%endif",
                    "%global with_hard_gcc_version_requirement 0",
                    "%global annobin_source_dir %{?_scl_root}/%{_usrsrc}/annobin",
                    "%if %{bootstrapping}",
                    "BuildRequires: gcc gcc-c++",
                    "%define gcc_for_annobin /usr/bin/gcc",
                    "%define gxx_for_annobin /usr/bin/g++",
                    "%else",
                    "BuildRequires: %{?scl_prefix}gcc",
                    "BuildRequires: %{?scl_prefix}gcc-c++",
                    "BuildRequires: %{?scl_prefix}annobin-plugin-gcc",
                    "%define gcc_for_annobin %{?_scl_root}/usr/bin/gcc",
                    "%define gxx_for_annobin %{?_scl_root}/usr/bin/g++",
                    "%endif",
                    "#---------------------------------------------------------------------------------",
                    "",
                    "# Make sure that the necessary sub-packages are built.",
                    "%if %{with gccplugin}",
                    "Requires: %{name}-plugin-gcc",
                    "%endif",
                    "",
                    "%build",
                    "%set_build_flags",
                    "export CFLAGS=\"$CFLAGS $RPM_OPT_FLAGS %build_cflags -I%{?_scl_root}/usr/include\"",
                    "export LDFLAGS=\"$LDFLAGS %build_ldflags -L%{?_scl_root}/usr/lib64 -L%{?_scl_root}/usr/lib\"",
                    "%if %{with plugin_rebuild}",
                    "# Rebuild the plugin(s), this time using the plugin itself!  This",
                    "# ensures that the plugin works, and that it contains annotations",
                    "# of its own.",
                    "",
                    "%if %{with gccplugin}",
                    "cp gcc-plugin/.libs/annobin.so.0.0.0 %{_tmppath}/tmp_annobin.so",
                    "make -C gcc-plugin clean",
                    "BUILD_FLAGS=\"-fplugin=%{_tmppath}/tmp_annobin.so\"",
                    "",
                    "# Disable the standard annobin plugin so that we do get conflicts.",
                    "%if 0%{?rhel} && 0%{?rhel} < 9",
                    "OPTS=\"$(rpm --eval '%undefine _annotated_build %build_cflags %build_ldflags')\"",
                    "%else",
                    "OPTS=\"$(rpm --undefine=_annotated_build --eval '%build_cflags %build_ldflags')\"",
                    "%endif",
                    "",
                    "make -C gcc-plugin CXXFLAGS=\"$OPTS $BUILD_FLAGS\"",
                    "rm %{_tmppath}/tmp_annobin.so",
                    "%endif",
                    "%endif",
                ]
            )
        )
        self.assertIn("%bcond_with clangplugin", rendered)
        self.assertIn("%bcond_with llvmplugin", rendered)
        self.assertIn("%bcond_with plugin_rebuild", rendered)
        self.assertIn("%undefine _annotated_build", rendered)
        self.assertIn("%global with_hard_gcc_version_requirement 1", rendered)
        self.assertNotIn("BuildRequires: %{?scl_prefix}annobin-plugin-gcc", rendered)
        self.assertIn("BuildRequires: %{?scl_prefix}gcc", rendered)
        self.assertIn("export CFLAGS=\"$CFLAGS $RPM_OPT_FLAGS -I%{?_scl_root}/usr/include\"", rendered)
        self.assertIn("export CXXFLAGS=\"$CXXFLAGS $RPM_OPT_FLAGS -I%{?_scl_root}/usr/include\"", rendered)
        self.assertIn("export LDFLAGS=\"$LDFLAGS %{?__global_ldflags} -L%{?_scl_root}/usr/lib64 -L%{?_scl_root}/usr/lib\"", rendered)

    def test_make_rewrite_sets_scl_and_bootstrap_compiler(self):
        rendered = rewrite_make(
            "\n".join(
                [
                    "%global __python /usr/bin/python3",
                    "%{?scl:%{?scl_package:%scl_package make}}",
                    "BuildRequires: gcc",
                    "%build",
                    "",
                    "%configure \\",
                    "\t--without-guile",
                ]
            )
        )
        self.assertIn("%global scl devtoolset-14", rendered)
        self.assertIn("BuildRequires: devtoolset-11-gcc", rendered)
        self.assertIn("export CC=/opt/rh/devtoolset-11/root/usr/bin/gcc", rendered)
        self.assertIn("%{?scl:%{?scl_package:%scl_package make}}", rendered)

    def test_elfutils_rewrite_sets_scl_and_bootstrap_compilers(self):
        rendered = rewrite_elfutils(
            "\n".join(
                [
                    "%global __python /usr/bin/python3",
                    "%{?scl:%{?scl_package:%scl_package elfutils}}",
                    "BuildRequires: gcc",
                    "BuildRequires: gcc-c++",
                    "%prep",
                    "%setup -q -n elfutils-%{version}",
                    "%build",
                    "trap 'cat config.log' EXIT",
                    "%configure CFLAGS=\"$RPM_OPT_FLAGS -fexceptions\"",
                    "%install",
                    "rm -rf ${RPM_BUILD_ROOT}",
                    "%make_install",
                    "",
                    "chmod +x ${RPM_BUILD_ROOT}%{_prefix}/%{_lib}/lib*.so*",
                ]
            )
        )
        self.assertIn("%global scl devtoolset-14", rendered)
        self.assertIn("BuildRequires: devtoolset-11-gcc", rendered)
        self.assertIn("BuildRequires: devtoolset-11-gcc-c++", rendered)
        self.assertIn("export CC=/opt/rh/devtoolset-11/root/usr/bin/gcc", rendered)
        self.assertIn("export CXX=/opt/rh/devtoolset-11/root/usr/bin/g++", rendered)
        self.assertIn("export PATH=%{_sourcedir}/builddeps/gettext-devel/usr/bin:$PATH", rendered)
        self.assertIn("export gettext_datadir=%{_sourcedir}/builddeps/gettext-devel/usr/share/gettext", rendered)
        self.assertIn('--disable-debuginfod', rendered)
        self.assertNotIn("%package debuginfod-client", rendered)
        self.assertNotIn("BuildRequires: pkgconfig(libmicrohttpd)", rendered)
        self.assertNotIn("Source8: libdebuginfod.so", rendered)
        self.assertIn("rm -f ${RPM_BUILD_ROOT}%{_bindir}/debuginfod-find", rendered)
        self.assertIn("rm -f ${RPM_BUILD_ROOT}%{_libdir}/libdebuginfod*", rendered)
        self.assertIn("%{?scl:%{?scl_package:%scl_package elfutils}}", rendered)


if __name__ == "__main__":
    unittest.main()
