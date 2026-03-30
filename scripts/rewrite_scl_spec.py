#!/usr/bin/env python3
"""Rewrite Rocky 8 gcc-toolset specs into EL7 devtoolset specs."""

import argparse
import re
import sys
from pathlib import Path


UPSTREAM_TOOLSET = "gcc-toolset-14"
TARGET_TOOLSET = "devtoolset-14"
UPSTREAM_BOOTSTRAP_TOOLSET = "gcc-toolset-13"
TARGET_BOOTSTRAP_TOOLSET = "devtoolset-11"
UPSTREAM_PREFIX = "/opt/rh/{}/root".format(UPSTREAM_TOOLSET)
TARGET_PREFIX = "/opt/rh/{}/root".format(TARGET_TOOLSET)
TARGET_BOOTSTRAP_PREFIX = "/opt/rh/{}/root".format(TARGET_BOOTSTRAP_TOOLSET)
TARGET_SCL_DEFINE = "%global scl {}\n".format(TARGET_TOOLSET)

GCC_MACRO_BLOCK = """\
%global devtoolset14_el7 1
%global devtoolset14_target x86_64-redhat-linux
%global devtoolset14_languages c,c++,fortran
%global devtoolset14_disable_multilib 1
%global devtoolset14_disable_tsan 0
%global devtoolset14_keep_asan 1
%global devtoolset14_keep_ubsan 1

"""
EL7_LIBSTDCXX_PATCH = "gcc14-libstdc++-compat-el7.patch"
EL7_LIBSTDCXX_PATCH_NUMBER = 1002
EL7_TLS_DTOR_XFAIL_PATCH = (
    "0019-XFAIL-thread_local-order2-when-TLS-dtor-order-is-not-correct.patch"
)
EL7_TLS_DTOR_XFAIL_PATCH_NUMBER = 3019
SET_BUILD_FLAGS_FALLBACK = """\
%{!?set_build_flags:%global set_build_flags CFLAGS="${CFLAGS:-%{optflags}}"; CXXFLAGS="${CXXFLAGS:-%{optflags}}"; FFLAGS="${FFLAGS:-%{optflags}}"; FCFLAGS="${FCFLAGS:-%{optflags}}"; LDFLAGS="${LDFLAGS:-%{?__global_ldflags}}"; export CFLAGS CXXFLAGS FFLAGS FCFLAGS LDFLAGS}

"""
BOOTSTRAP_ENV_BLOCK = """\
export PATH={prefix}/usr/bin:$PATH
export CC={prefix}/usr/bin/gcc
export CXX={prefix}/usr/bin/g++
export AR={prefix}/usr/bin/gcc-ar
export NM={prefix}/usr/bin/gcc-nm
export RANLIB={prefix}/usr/bin/gcc-ranlib
""".format(prefix=TARGET_BOOTSTRAP_PREFIX)


def rewrite_generic(text):
    text = (
        text.replace(UPSTREAM_BOOTSTRAP_TOOLSET + "-", TARGET_BOOTSTRAP_TOOLSET + "-")
        .replace(UPSTREAM_BOOTSTRAP_TOOLSET, TARGET_BOOTSTRAP_TOOLSET)
        .replace(UPSTREAM_TOOLSET, TARGET_TOOLSET)
        .replace(UPSTREAM_PREFIX, TARGET_PREFIX)
    )
    text = text.replace("%{build_ldflags}", "%{?__global_ldflags}")
    if "%set_build_flags" in text and SET_BUILD_FLAGS_FALLBACK not in text:
        text = SET_BUILD_FLAGS_FALLBACK + text
    return text


def inject_scl_define(text):
    if re.search(r"(?m)^%global scl\s+\S+", text):
        return text
    marker = re.search(r"(?m)^%\{\?scl:%\{\?scl_package:%scl_package [^}]+\}\}\n", text)
    if marker:
        return text[: marker.start()] + TARGET_SCL_DEFINE + text[marker.start() :]
    return TARGET_SCL_DEFINE + text


def inject_macros(text):
    if "%global devtoolset14_el7 1" in text:
        return text
    return GCC_MACRO_BLOCK + text


def strip_libgccjit(text):
    replacements = (
        (
            r"\n%package -n %\{\?scl_prefix\}libgccjit\n.*?\n%package -n libquadmath\n",
            "\n%package -n libquadmath\n",
        ),
        (
            r"\n# Build libgccjit separately, so that normal compiler binaries aren't -fpic\n.*?\ncd \.\.\n\n",
            "\n",
        ),
        (
            r"\nrm -f \$FULLEPATH/libgccjit\.so\nmkdir -p %\{buildroot\}%\{_prefix\}/%\{_lib\}/\ncp -a objlibgccjit/gcc/libgccjit\.so\.\* %\{buildroot\}%\{_prefix\}/%\{_lib\}/\nrm -f \$FULLPATH/libgccjit\.so\necho '/\* GNU ld script \*/\n%\{oformat\}\nINPUT \( %\{_prefix\}/%\{_lib\}/libgccjit\.so\.0 \)' > \$FULLPATH/libgccjit\.so\ncp -a \.\./gcc/jit/libgccjit\*\.h \$FULLPATH/include/\n/usr/bin/install -c -m 644 objlibgccjit/gcc/doc/libgccjit\.info %\{buildroot\}/%\{_infodir\}/\ngzip -9 %\{buildroot\}/%\{_infodir\}/libgccjit\.info\n",
            "\n",
        ),
        (
            r"\n%post -n %\{\?scl_prefix\}libgccjit -p /sbin/ldconfig\n.*?\n%post -n libquadmath\n",
            "\n%post -n libquadmath\n",
        ),
        (
            r"\n%files -n %\{\?scl_prefix\}libgccjit\n.*?\n%files plugin-devel\n",
            "\n%files plugin-devel\n",
        ),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.S)
    for pattern in (
        r"echo '/\* GNU ld script \*/\n%\{oformat2\}\nINPUT \( %\{_prefix\}/lib64/libgccjit\.so\.0 \)' > 64/libgccjit\.so\n",
        r"echo '/\* GNU ld script \*/\n%\{oformat2\}\nINPUT \( %\{_prefix\}/lib/libgccjit\.so\.0 \)' > 32/libgccjit\.so\n",
        r"%\{_prefix\}/lib/gcc/%\{gcc_target_platform\}/%\{gcc_major\}/32/libgccjit\.so\n",
    ):
        text = re.sub(pattern, "", text)
    return text


def rewrite_gcc(text):
    libcc1_relink_block = (
        "echo '/* GNU ld script\n"
        "   Use the shared library, but some functions are only in\n"
        "   the static library, so try that secondarily.  */\n"
        "%{oformat}\n"
        "INPUT ( %{?scl:%{_root_prefix}}%{!?scl:%{_prefix}}/%{_lib}/libstdc++.so.6 -lstdc++_nonshared%{nonsharedver} )' \\\n"
        "  > %{gcc_target_platform}/libstdc++-v3/src/.libs/libstdc++_system.so\n\n"
        "# Relink libcc1 against -lstdc++_nonshared:\n"
        "sed -i -e '/^postdeps/s/-lstdc++/-lstdc++_system/' libcc1/libtool\n"
        "rm -f libcc1/libcc1.la\n"
        "make -C libcc1 libcc1.la\n\n"
    )

    def force_macro(name, value):
        pattern = r"(?m)^%global {} [01]$".format(re.escape(name))
        return lambda data: re.sub(pattern, "%global {} {}".format(name, value), data)

    text = rewrite_generic(text)
    text = inject_macros(text)
    text = re.sub(
        r"--enable-languages=[^\s\\]+",
        "--enable-languages=%{devtoolset14_languages}",
        text,
    )
    text = text.replace(
        "--enable-shared --enable-threads=posix --enable-checking=release \\",
        "--enable-shared --enable-threads=posix --enable-checking=release \\\n\t--with-default-libstdcxx-abi=gcc4-compatible \\",
    )
    text = text.replace("--enable-multilib", "--disable-multilib")
    text = re.sub(
        r"(?m)^%global multilib_64_archs (.+)$",
        lambda match: "%global multilib_64_archs {}".format(
            " ".join(
                arch for arch in match.group(1).split() if arch != "x86_64"
            )
        ),
        text,
    )
    for name, value in (
        ("build_d", 0),
        ("build_m2", 0),
        ("build_libhwasan", 0),
        ("build_liblsan", 1),
        ("build_libtsan", 1),
        ("build_offload_nvptx", 0),
        ("build_offload_amdgcn", 0),
        ("build_libasan", 1),
        ("build_libubsan", 1),
    ):
        text = force_macro(name, value)(text)
    text = text.replace(
        "%ifarch %{multilib_64_archs}\n# Ensure glibc{,-devel} is installed for both multilib arches\nBuildRequires: /lib/libc.so.6 /usr/lib/libc.so /lib64/libc.so.6 /usr/lib64/libc.so\n%endif\n",
        "",
    )
    text = re.sub(
        r"\n%ifarch %\{multilib_64_archs\}\nln -sf /lib/libgcc_s\.so\.1 \$FULLPATH/32/libgcc_s\.so\n%endif\n",
        "\n",
        text,
    )
    text = re.sub(
        r"\n%ifarch %\{multilib_64_archs\}\nrm -f \$FULLPATH/32/libgcc_s\.so\necho '/\* GNU ld script\n   Use the shared library, but some functions are only in\n   the static library, so try that secondarily\.  \*/\n%\{oformat2\}\nGROUP \( /lib/libgcc_s\.so\.1 libgcc\.a \)' > \$FULLPATH/32/libgcc_s\.so\n%endif\n",
        "\n",
        text,
    )
    text = re.sub(
        r"(?m)^%\{_prefix\}/lib/gcc/%\{gcc_target_platform\}/%\{gcc_major\}/32/libgcc_s\.so\n?",
        "",
        text,
    )
    text = text.replace(
        "Requires: libubsan%{_isa} >= 8.3.1",
        "Requires: libubsan1%{_isa} >= 8.3.1",
    )
    text = text.replace("%package -n libtsan2", "%package -n libtsan")
    text = text.replace("%description -n libtsan2", "%description -n libtsan")
    text = text.replace("Requires: libtsan2%{_isa} >= 12.1.1", "Requires: libtsan%{_isa} >= 5.1.1")
    text = text.replace("%post -n libtsan2 -p /sbin/ldconfig", "%post -n libtsan -p /sbin/ldconfig")
    text = text.replace("%postun -n libtsan2 -p /sbin/ldconfig", "%postun -n libtsan -p /sbin/ldconfig")
    text = text.replace("%files -n libtsan2", "%files -n libtsan")
    text = text.replace(
        "%package gfortran\n"
        "Summary: Fortran support for GCC %{gcc_major}\n"
        "Requires: %{?scl_prefix}gcc%{!?scl:13} = %{version}-%{release}\n"
        "Requires: libgfortran >= 8.1.1\n",
        "%package gfortran\n"
        "Summary: Fortran support for GCC %{gcc_major}\n"
        "Requires: %{?scl_prefix}gcc%{!?scl:13} = %{version}-%{release}\n"
        "%if 0%{?rhel} > 7\n"
        "Requires: libgfortran >= 8.1.1\n"
        "%else\n"
        "Requires: libgfortran5 >= 8.1.1\n"
        "%endif\n",
        1,
    )
    text = text.replace(
        "%install\nrm -rf %{buildroot}\nmkdir -p %{buildroot}\n",
        "%install\nrm -rf %{buildroot}\nmkdir -p %{buildroot}\nmkdir -p %{buildroot}%{_docdir}\n",
        1,
    )
    text = text.replace(
        "rm -f %{buildroot}%{_prefix}/%{_lib}/libssp*\n"
        "rm -f %{buildroot}%{_prefix}/%{_lib}/libvtv* || :\n",
        "rm -f %{buildroot}%{_prefix}/%{_lib}/libssp*\n"
        "rm -f %{buildroot}%{_prefix}/%{_lib}/libvtv* || :\n"
        "rm -f %{buildroot}%{_prefix}/%{_lib}/libhwasan* || :\n"
        "rm -f $FULLPATH/libhwasan* || :\n"
        "rm -f %{buildroot}%{_prefix}/%{_lib}/libgcc_s.so || :\n"
        "rm -f %{buildroot}%{_infodir}/libgomp.info* %{buildroot}%{_infodir}/libitm.info* %{buildroot}%{_infodir}/libquadmath.info* || :\n"
        "rm -f %{buildroot}%{_mandir}/man7/fsf-funding.7* %{buildroot}%{_mandir}/man7/gfdl.7* %{buildroot}%{_mandir}/man7/gpl.7* || :\n"
        "rm -rf %{buildroot}%{_prefix}/lib/gcc/%{gcc_target_platform}/%{gcc_major}/include/ssp || :\n"
        "rm -f %{buildroot}%{_prefix}/libexec/getconf/default || :\n"
        "rm -f %{buildroot}%{_root_prefix}/%{_lib}/libitm.so.1* %{buildroot}%{_root_prefix}/%{_lib}/libatomic.so.1* || :\n"
        "find %{buildroot}%{_prefix}/share/gcc-%{gcc_major}/python %{buildroot}%{_datadir}/gdb/auto-load/%{_prefix}/%{_lib} -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || :\n"
        "rm -rf %{buildroot}%{_prefix}/share/locale || :\n",
        1,
    )
    text = text.replace(
        "%{_prefix}/bin/gcc-ar\n%{_prefix}/bin/gcc-nm\n%{_prefix}/bin/gcc-ranlib\n",
        "%{_prefix}/bin/gcc-ar\n%{_prefix}/bin/gcc-nm\n%{_prefix}/bin/gcc-ranlib\n"
        "%{_prefix}/bin/%{gcc_target_platform}-gcc-ar\n"
        "%{_prefix}/bin/%{gcc_target_platform}-gcc-nm\n"
        "%{_prefix}/bin/%{gcc_target_platform}-gcc-ranlib\n",
        1,
    )
    text = re.sub(
        r"\n%if 0\n(%files gdb-plugin\n(?:.*\n)*?)%endif\n",
        r"\n\1",
        text,
        count=1,
    )
    text = text.replace(
        "%{_prefix}/libexec/gcc/%{gcc_target_platform}/%{gcc_major}/cc1\n"
        "%{_prefix}/libexec/gcc/%{gcc_target_platform}/%{gcc_major}/collect2\n",
        "%{_prefix}/libexec/gcc/%{gcc_target_platform}/%{gcc_major}/cc1\n"
        "%{_prefix}/libexec/gcc/%{gcc_target_platform}/%{gcc_major}/collect2\n"
        "%{_prefix}/lib/gcc/%{gcc_target_platform}/%{gcc_major}/include-fixed\n"
        "%{_prefix}/lib/gcc/%{gcc_target_platform}/%{gcc_major}/install-tools\n"
        "%{_prefix}/libexec/gcc/%{gcc_target_platform}/%{gcc_major}/install-tools\n",
        1,
    )
    text = text.replace(
        "%doc rpm.doc/changelogs/libstdc++-v3/ChangeLog* libstdc++-v3/README*\n",
        "%doc rpm.doc/changelogs/libstdc++-v3/ChangeLog* libstdc++-v3/README*\n"
        "%{_datadir}/gcc-%{gcc_major}/python/libstdcxx\n"
        "%{_datadir}/gdb/auto-load/%{_prefix}/%{_lib}/libstdc++*gdb.py*\n"
        "%{_datadir}/gdb/auto-load/%{_prefix}/%{_lib}/__pycache__/libstdc++*gdb*.pyc\n",
        1,
    )
    text = text.replace(
        "for f in `find %{buildroot}%{_prefix}/share/gcc-%{gcc_major}/python/ \\\n"
        "\t       %{buildroot}%{_datadir}/gdb/auto-load/%{_prefix}/%{_lib}/ -name \\*.py`; do\n"
        "  r=${f/$RPM_BUILD_ROOT/}\n"
        "  %{__python3} -c 'import py_compile; py_compile.compile(\"'$f'\", dfile=\"'$r'\")'\n"
        "  %{__python3} -O -c 'import py_compile; py_compile.compile(\"'$f'\", dfile=\"'$r'\")'\n"
        "done\n\n",
        "for f in `find %{buildroot}%{_prefix}/share/gcc-%{gcc_major}/python/ \\\n"
        "\t       %{buildroot}%{_datadir}/gdb/auto-load/%{_prefix}/%{_lib}/ -name \\*.py`; do\n"
        "  r=${f/$RPM_BUILD_ROOT/}\n"
        "  %{__python3} -c 'import py_compile; py_compile.compile(\"'$f'\", dfile=\"'$r'\")'\n"
        "  %{__python3} -O -c 'import py_compile; py_compile.compile(\"'$f'\", dfile=\"'$r'\")'\n"
        "done\n"
        "find %{buildroot}%{_prefix}/share/gcc-%{gcc_major}/python %{buildroot}%{_datadir}/gdb/auto-load/%{_prefix}/%{_lib} -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || :\n\n",
        1,
    )
    text = text.replace(libcc1_relink_block + "# Test the nonshared bits.\n", "# Test the nonshared bits.\n")
    text = text.replace(
        "%ifarch sparc sparcv9 sparc64\n"
        "make %{?_smp_mflags} BOOT_CFLAGS=\"$OPT_FLAGS\" LDFLAGS_FOR_TARGET=-Wl,-z,relro,-z,now bootstrap\n"
        "%else\n"
        "make %{?_smp_mflags} BOOT_CFLAGS=\"$OPT_FLAGS\" LDFLAGS_FOR_TARGET=-Wl,-z,relro,-z,now profiledbootstrap\n"
        "%endif\n\n",
        "%ifarch sparc sparcv9 sparc64\n"
        "make %{?_smp_mflags} BOOT_CFLAGS=\"$OPT_FLAGS\" LDFLAGS_FOR_TARGET=-Wl,-z,relro,-z,now bootstrap\n"
        "%else\n"
        "make %{?_smp_mflags} BOOT_CFLAGS=\"$OPT_FLAGS\" LDFLAGS_FOR_TARGET=-Wl,-z,relro,-z,now profiledbootstrap\n"
        "%endif\n\n"
        + libcc1_relink_block,
        1,
    )
    text = text.replace(
        "mkdir -p rpm.doc/changelogs/{gcc/cp,gcc/jit,libstdc++-v3,libgomp,libatomic,libsanitizer}\n\n"
        "for i in {gcc,gcc/cp,gcc/jit,libstdc++-v3,libgomp,libatomic,libsanitizer}/ChangeLog*; do\n",
        "mkdir -p rpm.doc/changelogs/{gcc/cp,gcc/jit,libstdc++-v3,libgomp,libcc1,libatomic,libsanitizer}\n\n"
        "for i in {gcc,gcc/cp,gcc/jit,libstdc++-v3,libgomp,libcc1,libatomic,libsanitizer}/ChangeLog*; do\n",
        1,
    )
    text = text.replace(
        "%ifarch %{multilib_64_archs}\n"
        "`cat $(find %{gcc_target_platform}/32/libstdc++-v3/include -name c++config.h)`\n"
        "%else\n"
        "`cat $(find %{gcc_target_platform}/libstdc++-v3/include -name c++config.h)`\n"
        "%endif\n"
        "#else\n"
        "%ifarch %{multilib_64_archs}\n"
        "`cat $(find %{gcc_target_platform}/libstdc++-v3/include -name c++config.h)`\n"
        "%else\n"
        "`cat $(find %{gcc_target_platform}/64/libstdc++-v3/include -name c++config.h)`\n"
        "%endif\n",
        "`cat $(find %{gcc_target_platform}/libstdc++-v3/include -name c++config.h)`\n"
        "#else\n"
        "`cat $(find %{gcc_target_platform}/libstdc++-v3/include -name c++config.h)`\n",
    )
    patch_decl = "Patch{}: {}".format(EL7_LIBSTDCXX_PATCH_NUMBER, EL7_LIBSTDCXX_PATCH)
    if patch_decl not in text:
        text = text.replace(
            "Patch1000: gcc14-libstdc++-compat.patch",
            "Patch1000: gcc14-libstdc++-compat.patch\n{}".format(patch_decl),
            1,
        )
    patch_apply = "%patch -P{} -p0 -b .libstdc++-compat-el7~".format(
        EL7_LIBSTDCXX_PATCH_NUMBER
    )
    if patch_apply not in text:
        text = text.replace(
            "%patch -P1000 -p0 -b .libstdc++-compat~",
            "%patch -P1000 -p0 -b .libstdc++-compat~\n{}".format(patch_apply),
            1,
        )
    dts_patch_decl = "Patch{}: {}".format(
        EL7_TLS_DTOR_XFAIL_PATCH_NUMBER, EL7_TLS_DTOR_XFAIL_PATCH
    )
    if dts_patch_decl not in text:
        if "Patch3018: 0021-libstdc++-disable-tests.patch" in text:
            text = text.replace(
                "Patch3018: 0021-libstdc++-disable-tests.patch",
                "Patch3018: 0021-libstdc++-disable-tests.patch\n{}".format(
                    dts_patch_decl
                ),
                1,
            )
        else:
            text = text.replace(patch_decl, "{}\n{}".format(patch_decl, dts_patch_decl), 1)
    dts_patch_apply = "%patch -P{} -p1 -b .dts-test-19~".format(
        EL7_TLS_DTOR_XFAIL_PATCH_NUMBER
    )
    if dts_patch_apply not in text:
        if "%patch -P3018 -p1 -b .dts-test-18~" in text:
            text = text.replace(
                "%patch -P3018 -p1 -b .dts-test-18~",
                "%patch -P3018 -p1 -b .dts-test-18~\n{}".format(dts_patch_apply),
                1,
            )
        else:
            text = text.replace(patch_apply, "{}\n{}".format(patch_apply, dts_patch_apply), 1)
    text = strip_libgccjit(text)
    return text


def rewrite_make(text):
    text = rewrite_generic(text)
    text = inject_scl_define(text)
    text = text.replace(
        "BuildRequires: gcc\n",
        "BuildRequires: {}-gcc\n".format(TARGET_BOOTSTRAP_TOOLSET),
        1,
    )
    build_marker = "%build\n"
    if build_marker in text and BOOTSTRAP_ENV_BLOCK not in text:
        text = text.replace(build_marker, build_marker + BOOTSTRAP_ENV_BLOCK + "\n", 1)
    return text


def rewrite_strace(text):
    text = rewrite_generic(text)
    text = inject_scl_define(text)
    text = text.replace("Version: 5.13", "Version: 6.12", 1)
    text = text.replace(
        "BuildRequires: gcc gzip make\n",
        "BuildRequires: {}-gcc gzip make\n".format(TARGET_BOOTSTRAP_TOOLSET),
        1,
    )
    for dep in (
        "BuildRequires: libacl-devel, time\n",
        "BuildRequires: pkgconfig(bluez)\n",
    ):
        text = text.replace(dep, "")
    old_patches = """# v5.13-6-gba1ca1e \"tests: relax -a check in prlimit64 test\"\nPatch139: 0139-tests-relax-a-check-in-prlimit64-test.patch\n# v5.13-5-ge4feb6b \"tests: move DIAG_PUSH_IGNORE_NONNULL/DIAG_POP_IGNORE_NONNULL outside main\"\nPatch140: 0140-tests-move-DIAG_PUSH_IGNORE_NONNULL-DIAG_POP_IGNORE_.patch\n# v5.13-55-g6b2191f \"filter_qualify: free allocated data on the error path exit of parse_poke_token\"\nPatch150: 0150-filter_qualify-free-allocated-data-on-the-error-path.patch\n# v5.13-56-g80dc60c \"macros: expand BIT macros, add MASK macros; add *_SAFE macros\"\nPatch151: 0151-macros-expand-BIT-macros-add-MASK-macros-add-_SAFE-m.patch\n# v5.13-58-g94ae5c2 \"trie: use BIT* and MASK* macros\"\nPatch152: 0152-trie-use-BIT-and-MASK-macros.patch\n# v5.13-65-g41b753e \"tee: rewrite num_params access in tee_fetch_buf_data\"\nPatch153: 0153-tee-rewrite-num_params-access-in-tee_fetch_buf_data.patch\n\n## RHEL7-only: headers on some builders do not provide O_TMPFILE\nPatch2000: 2000-strace-provide-O_TMPFILE-fallback-definition.patch\n## RHEL-only: aarch64 brew builders are extremely slow on qual_fault.test\nPatch2001: 2001-limit-qual_fault-scope-on-aarch64.patch\n## RHEL-only: avoid ARRAY_SIZE macro re-definition in libiberty.h\nPatch2003: 2003-undef-ARRAY_SIZE.patch\n## RHEL7-only: mark ipc_shm.gen test as XFAIL due to\n## https://bugzilla.redhat.com/1978412\nPatch2005: 2005-mark-ipc_shm-ipc_msg-XFAIL-on-ppc64.patch\n"""
    new_patches = """# Origin: https://github.com/strace/strace/commit/ba41bc0da4b841d9343b7644a3d8c3bd5e3f2780\nPatch0001: 0001-tests-Skip-legacy_syscall_info-on-riscv64-with-kerne.patch\n\n# Origin: https://github.com/strace/strace/commit/189655e7a0603953393057f051ecc71cad3fa42e\nPatch0002: 0002-tests-Reduce-expected-precision-for-relative-timesta.patch\n\n# Origin: https://github.com/strace/strace/commit/1e4f282ba6c1fea8b689aa74affbedddbb799d21\nPatch0003: 0003-tests-group_req-fix-compilation-warnings.patch\n"""
    text = text.replace(old_patches, new_patches, 1)
    old_prep = """%patch139 -p1\n%patch140 -p1\n%patch150 -p1\n%patch151 -p1\n%patch152 -p1\n%patch153 -p1\n\n%patch2000 -p1\n%patch2001 -p1\n%patch2003 -p1\n%patch2005 -p1\n\necho -n %version-%release > .tarball-version\necho -n 2020 > .year\necho -n 2021-05-14 > doc/.strace.1.in.date\n"""
    new_prep = """%patch0001 -p1\n%patch0002 -p1\n%patch0003 -p1\n\necho -n %version-%release > .tarball-version\necho -n 2024 > .year\necho -n 2023-11-21 > doc/.strace.1.in.date\necho -n 2022-01-01 > doc/.strace-log-merge.1.in.date\n"""
    text = text.replace(old_prep, new_prep, 1)
    text = text.replace(
        "%configure --enable-mpers=check --with-libdw ac_cv_member_struct_perf_event_attr_context_switch=no",
        'export libdw_LIBS="-lzstd ${libdw_LIBS:-}"\n'
        "%configure --enable-mpers=check --with-libdw --enable-bundled=yes ac_cv_member_struct_perf_event_attr_context_switch=no",
        1,
    )
    build_marker = "%build\n"
    if build_marker in text and BOOTSTRAP_ENV_BLOCK not in text:
        text = text.replace(build_marker, build_marker + BOOTSTRAP_ENV_BLOCK + "\n", 1)
    return text


def rewrite_valgrind(text):
    text = rewrite_generic(text)
    text = inject_scl_define(text)
    text = text.replace("Version: 3.17.0", "Version: 3.26.0", 1)
    text = text.replace("Release: 4%{?dist}", "Release: 5%{?dist}", 1)
    text = text.replace("URL: http://www.valgrind.org/", "URL: https://www.valgrind.org/", 1)
    text = text.replace(
        "BuildRequires: gcc-c++\n",
        "BuildRequires: {}-gcc-c++\nBuildRequires: {}-gcc\n".format(
            TARGET_BOOTSTRAP_TOOLSET, TARGET_BOOTSTRAP_TOOLSET
        ),
        1,
    )
    if "BuildRequires: python3-devel\n" not in text:
        text = text.replace(
            "# For make check validating the documentation\nBuildRequires: docbook-dtds\n\n",
            "# For make check validating the documentation\nBuildRequires: docbook-dtds\n\n"
            "# For running the testsuite.\n"
            "BuildRequires: python3-devel\n\n",
            1,
        )
    old_patches = """# Needs investigation and pushing upstream\nPatch1: valgrind-3.9.0-cachegrind-improvements.patch\n\n# KDE#211352 - helgrind races in helgrind's own mythread_wrapper\nPatch2: valgrind-3.9.0-helgrind-race-supp.patch\n\n# Make ld.so supressions slightly less specific.\nPatch3: valgrind-3.9.0-ldso-supp.patch\n\n# Add some stack-protector\nPatch4: valgrind-3.16.0-some-stack-protector.patch\n\n# Add some -Wl,z,now.\nPatch5: valgrind-3.16.0-some-Wl-z-now.patch\n\n# Upstream commits that provide additional ppc64le ISA 3.1 support\n# commit 3cc0232c46a5905b4a6c2fbd302b58bf5f90b3d5\n# PPC64: ISA 3.1 VSX PCV Generate Operations\n# commit 078f89e99b6f62e043f6138c6a7ae238befc1f2a\n# PPC64: Reduced-Precision bfloat16 Outer Product & Format Conversion Operations\n# commit e09fdaf569b975717465ed8043820d0198d4d47d\n# PPC64: Reduced-Precision: Missing Integer-based Outer Product Operations\nPatch6: valgrind-3.17.0-ppc64-isa-3.1.patch\n\n# Upstream commits that provide extra tests for ppc64le ISA 3.1 support\n# commit c8fa838be405d7ac43035dcf675bf490800c26ec\n# Reduced Precision bfloat16 outer product tests\n# commit 4bcc6c8a97c10c4dd41b35bd3b3035ec4037d524\n# VSX Permute Control Vector Generate Operation tests.\n# commit c589b652939655090c005a982a71f50c489fb5ce\n# Reduced precision Missing Integer based outer tests\nPatch7: valgrind-3.17.0-ppc64-isa-3.1-tests.patch\n\n# commit 45873298ff2d17accc65654d64758360616aade5\n# s390x: Add missing UNOP insns to s390_insn_as_string\nPatch8: valgrind-3.17.0-s390_insn_as_string.patch\n\n# KDE#435908 Don't look for separate debuginfo if image already has .debug_info\nPatch9: valgrind-3.17.0-debuginfod.patch\n\n# KDE#423963 Only process clone results in the parent thread\nPatch10: valgrind-3.17.0-clone-parent-res.patch\n"""
    new_patches = """# Needs investigation and pushing upstream\nPatch1: valgrind-3.9.0-cachegrind-improvements.patch\n\n# Make ld.so supressions slightly less specific.\nPatch2: valgrind-3.9.0-ldso-supp.patch\n\n# Add some stack-protector\nPatch3: valgrind-3.26.0-some-stack-protector.patch\n\n# Add some -Wl,z,now.\nPatch4: valgrind-3.26.0-some-Wl-z-now.patch\n\n# VALGRIND_3_26_BRANCH patches\nPatch5: 0001-Prepare-NEWS-for-branch-3.26-fixes.patch\nPatch6: 0002-Bug-511972-valgrind-3.26.0-tests-fail-to-build-on-up.patch\nPatch7: 0003-readlink-proc-self-exe-overwrites-buffer-beyond-its-.patch\nPatch8: 0004-Linux-DRD-suppression-add-an-entry-for-__is_decorate.patch\nPatch9: 0005-Linux-Helgrind-add-a-suppression-for-_dl_allocate_tl.patch\nPatch10: 0006-Disable-linux-madvise-MADV_GUARD_INSTALL.patch\nPatch11: 0007-Bug-514613-Unclosed-leak_summary-still_reachable-tag.patch\nPatch12: 0008-Bug-514206-Assertion-sr_isError-sr-failed-mmap-fd-po.patch\n\n# Refix for https://bugs.kde.org/show_bug.cgi?id=514613\nPatch100: 0001-Refix-still_reachable-xml-closing-tag-and-add-testca.patch\n"""
    text = text.replace(old_patches, new_patches, 1)
    old_prep = """%patch1 -p1\n%patch2 -p1\n%patch3 -p1\n\n# Old rhel gcc doesn't have -fstack-protector-strong.\n%if 0%{?fedora} || 0%{?rhel} >= 7\n%patch4 -p1\n%patch5 -p1\n%endif\n\n%patch6 -p1\n%patch7 -p1\n\n%patch8 -p1\n%patch9 -p1\n%patch10 -p1\n"""
    new_prep = """%patch1 -p1\n%patch2 -p1\n%patch3 -p1\n%patch4 -p1\n\n%patch5 -p1\n%patch6 -p1\n%patch7 -p1\n%patch8 -p1\n%patch9 -p1\n%patch10 -p1\n%patch11 -p1\n%patch12 -p1\n\n%patch100 -p1\n"""
    text = text.replace(old_prep, new_prep, 1)
    text = text.replace(
        "# LTO triggers undefined symbols in valgrind.  Valgrind has a --enable-lto\n# configure time option, but that doesn't seem to help.\n# Disable LTO for now.\n%define _lto_cflags %{nil}\n",
        "# LTO triggers undefined symbols in valgrind.  But valgrind has a\n# --enable-lto configure time option that we will use instead.\n%define _lto_cflags %{nil}\n",
        1,
    )
    text = text.replace(
        "%configure\n",
        "%configure \\\n  --enable-lto\n",
        1,
    )
    text = text.replace(
        "%files devel\n%dir %{_includedir}/valgrind\n%{_includedir}/valgrind/valgrind.h\n%{_includedir}/valgrind/callgrind.h\n%{_includedir}/valgrind/drd.h\n%{_includedir}/valgrind/helgrind.h\n%{_includedir}/valgrind/memcheck.h\n%{_includedir}/valgrind/dhat.h\n%{_libdir}/pkgconfig/valgrind.pc\n",
        "%files devel\n%dir %{_includedir}/valgrind\n%{_includedir}/valgrind/*\n%{_libdir}/pkgconfig/valgrind.pc\n",
        1,
    )
    text = text.replace(
        "rm -f docs/installed/*.ps\n",
        "rm -f docs/installed/*.ps\n"
        "rm -f $RPM_BUILD_ROOT%{_datadir}/gdb/auto-load/valgrind-monitor.py\n"
        "rm -f $RPM_BUILD_ROOT%{_datadir}/gdb/auto-load/valgrind-monitor-def.py\n"
        "rm -f $RPM_BUILD_ROOT%{_libexecdir}/valgrind/valgrind-monitor.py\n"
        "rm -f $RPM_BUILD_ROOT%{_libexecdir}/valgrind/valgrind-monitor-def.py\n",
        1,
    )
    build_marker = "%build\n"
    if build_marker in text and BOOTSTRAP_ENV_BLOCK not in text:
        text = text.replace(build_marker, build_marker + BOOTSTRAP_ENV_BLOCK + "\n", 1)
    return text

def rewrite_elfutils(text):
    text = rewrite_generic(text)
    text = inject_scl_define(text)
    text = text.replace(
        "BuildRequires: gcc-c++\n",
        "BuildRequires: {}-gcc-c++\n".format(TARGET_BOOTSTRAP_TOOLSET),
        1,
    )
    text = text.replace(
        "BuildRequires: gcc\n",
        "BuildRequires: {}-gcc\n".format(TARGET_BOOTSTRAP_TOOLSET),
        1,
    )
    build_marker = "%build\n"
    if build_marker in text and BOOTSTRAP_ENV_BLOCK not in text:
        text = text.replace(build_marker, build_marker + BOOTSTRAP_ENV_BLOCK + "\n", 1)
    prep_marker = "%prep\n%setup -q -n elfutils-%{version}\n"
    prep_inject = (
        "%prep\n%setup -q -n elfutils-%{version}\n\n"
        "if ! command -v autopoint >/dev/null 2>&1 && [ -x %{_sourcedir}/builddeps/gettext-devel/usr/bin/autopoint ]; then\n"
        "  export PATH=%{_sourcedir}/builddeps/gettext-devel/usr/bin:$PATH\n"
        "  export gettext_datadir=%{_sourcedir}/builddeps/gettext-devel/usr/share/gettext\n"
        "fi\n"
    )
    if prep_marker in text and "gettext_datadir=%{_sourcedir}/builddeps/gettext-devel/usr/share/gettext" not in text:
        text = text.replace(prep_marker, prep_inject, 1)
    for old in (
        "Recommends: %{?scl_prefix}elfutils-debuginfod-client%{depsuffix} = %{version}-%{release}\n",
        "Requires: %{?scl_prefix}elfutils-debuginfod-client%{depsuffix} = %{version}-%{release}\n",
        "Recommends: %{?scl_prefix}elfutils-debuginfod-client-devel%{depsuffix} = %{version}-%{release}\n",
        "Requires: %{?scl_prefix}elfutils-debuginfod-client-devel%{depsuffix} = %{version}-%{release}\n",
        "Requires: pkgconfig(libcurl) >= 7.29.0\n",
        "BuildRequires: pkgconfig(libmicrohttpd) >= 0.9.33\n",
        "BuildRequires: pkgconfig(libcurl) >= 7.29.0\n",
        "BuildRequires: pkgconfig(sqlite3) >= 3.7.17\n",
        "BuildRequires: pkgconfig(libarchive) >= 3.1.2\n",
        "BuildBuildRequires: pkgconfig(sqlite3) >= 3.7.17\n",
        "Source8: libdebuginfod.so\n",
        "Source9: libdebuginfod.a\n",
        "# For debuginfod\n"
        "BuildRequires: pkgconfig(libmicrohttpd) >= 0.9.33\n"
        "BuildRequires: pkgconfig(libcurl) >= 7.29.0\n"
        "BuildRequires: pkgconfig(sqlite3) >= 3.7.17\n"
        "BuildRequires: pkgconfig(libarchive) >= 3.1.2\n\n",
        "# For debuginfod\nBuild\n",
        "Build\n",
        "rm ${RPM_BUILD_ROOT}%{_sysconfdir}/profile.d/debuginfod.sh\n",
        "rm ${RPM_BUILD_ROOT}%{_sysconfdir}/profile.d/debuginfod.csh\n",
        "%ldconfig_scriptlets debuginfod-client\n",
        "%post debuginfod-client -p /sbin/ldconfig\n",
        "%postun debuginfod-client -p /sbin/ldconfig\n",
    ):
        text = text.replace(old, "")
    text = text.replace(
        '%configure CFLAGS="$RPM_OPT_FLAGS -fexceptions"',
        '%configure CFLAGS="$RPM_OPT_FLAGS -fexceptions" --disable-debuginfod',
        1,
    )
    debuginfod_cleanup = (
        "chmod +x ${RPM_BUILD_ROOT}%{_prefix}/%{_lib}/lib*.so*\n"
        "rm -f ${RPM_BUILD_ROOT}%{_sysconfdir}/profile.d/debuginfod.sh\n"
        "rm -f ${RPM_BUILD_ROOT}%{_sysconfdir}/profile.d/debuginfod.csh\n"
        "rm -f ${RPM_BUILD_ROOT}%{_bindir}/debuginfod-find\n"
        "rm -f ${RPM_BUILD_ROOT}%{_libdir}/libdebuginfod*\n"
        "rm -f ${RPM_BUILD_ROOT}%{_libdir}/pkgconfig/libdebuginfod.pc\n"
        "rm -f ${RPM_BUILD_ROOT}%{_includedir}/elfutils/debuginfod.h\n"
        "rm -f ${RPM_BUILD_ROOT}%{_mandir}/man1/debuginfod-find.1*\n"
        "rm -f ${RPM_BUILD_ROOT}%{_mandir}/man3/debuginfod_*.3*\n"
    )
    text = text.replace(
        "chmod +x ${RPM_BUILD_ROOT}%{_prefix}/%{_lib}/lib*.so*\n\n",
        debuginfod_cleanup + "\n",
        1,
    )
    text = text.replace(
        "chmod +x ${RPM_BUILD_ROOT}%{_prefix}/%{_lib}/lib*.so*\n",
        debuginfod_cleanup,
        1,
    )
    text = text.replace(
        "chmod +x ${RPM_BUILD_ROOT}%{_prefix}/%{_lib}/lib*.so*",
        debuginfod_cleanup.rstrip("\n"),
        1,
    )
    text = text.replace(
        "ls -ls $RPM_BUILD_ROOT%{_libdir}/lib{elf,dw,asm,debuginfod}.so\n"
        "rm -f $RPM_BUILD_ROOT%{_libdir}/lib{elf,dw,asm,debuginfod}.so\n"
        "install -p -m 644 %{SOURCE2} %{SOURCE3} %{SOURCE4} \\\n"
        "\t%{SOURCE5} %{SOURCE6} %{SOURCE7} %{SOURCE8} %{SOURCE9} \\\n"
        "\t$RPM_BUILD_ROOT%{_libdir}/\n",
        "ls -ls $RPM_BUILD_ROOT%{_libdir}/lib{elf,dw,asm}.so\n"
        "rm -f $RPM_BUILD_ROOT%{_libdir}/lib{elf,dw,asm}.so\n"
        "install -p -m 644 %{SOURCE2} %{SOURCE3} %{SOURCE4} \\\n"
        "\t%{SOURCE5} %{SOURCE6} %{SOURCE7} \\\n"
        "\t$RPM_BUILD_ROOT%{_libdir}/\n",
        1,
    )
    text = re.sub(
        r"\n%package debuginfod-client\n.*?\n%prep\n",
        "\n%prep\n",
        text,
        flags=re.S,
        count=1,
    )
    text = re.sub(
        r"\n%files debuginfod-client\n.*$",
        "\n",
        text,
        flags=re.S,
        count=1,
    )
    text = re.sub(
        r"%if 0%\{\?rhel\} >= 8 \|\| 0%\{\?fedora\} >= 20\n%else\n%endif\n",
        "",
        text,
    )
    return text


def rewrite_annobin(text):
    text = rewrite_generic(text)
    text = inject_scl_define(text)
    text = text.replace("%bcond_without clangplugin", "%bcond_with clangplugin")
    text = text.replace("%bcond_without llvmplugin", "%bcond_with llvmplugin")
    text = text.replace("%bcond_without plugin_rebuild", "%bcond_with plugin_rebuild")
    text = text.replace(
        "# %%if %%{without plugin_rebuild}\n# %%undefine _annotated_build\n# %%endif\n",
        "%if %{without plugin_rebuild}\n%undefine _annotated_build\n%endif\n",
        1,
    )
    text = text.replace(
        "%global with_hard_gcc_version_requirement 0",
        "%global with_hard_gcc_version_requirement 1",
        1,
    )
    text = text.replace(
        "Requires: (%{?scl_prefix}gcc >= %{gcc_major} with %{?scl_prefix}gcc < %{gcc_next})",
        "Requires: %{?scl_prefix}gcc >= %{gcc_major}, %{?scl_prefix}gcc < %{gcc_next}",
    )
    text = text.replace(
        "%global ANNOBIN_GCC_PLUGIN_DIR %(%gcc_for_annobin --print-file-name=plugin)",
        "%global ANNOBIN_GCC_PLUGIN_DIR %{_scl_root}/usr/lib/gcc/x86_64-redhat-linux/%{gcc_major}/plugin",
        1,
    )
    text = re.sub(
        r"%if %\{bootstrapping\}\n.*?%endif\n\n#---------------------------------------------------------------------------------\n\n# Make sure that the necessary sub-packages are built\.\n",
        "%{?scl:Requires:%scl_runtime}\n"
        "%{?scl:BuildRequires:%scl_runtime}\n"
        "%{?scl:BuildRequires:scl-utils-build}\n"
        "# We need the devtoolset-14 version of gcc to build annobin, as otherwise the versions will not match.\n"
        "%{?scl:Requires:%scl_require_package %{scl} gcc}\n\n"
        "BuildRequires: %{?scl_prefix}gcc\n\n"
        "%define gcc_for_annobin %{?_scl_root}/usr/bin/gcc\n"
        "%define gxx_for_annobin %{?_scl_root}/usr/bin/g++\n\n"
        "#---------------------------------------------------------------------------------\n\n# Make sure that the necessary sub-packages are built.\n",
        text,
        flags=re.S,
        count=1,
    )
    text = text.replace(
        "BuildRequires: %{?scl_prefix}annobin-plugin-gcc\n",
        "",
        1,
    )
    text = text.replace(
        "%global annobin_source_dir %{?_scl_root}/%{_usrsrc}/annobin\n",
        "",
        1,
    )
    text = text.replace(
        '%build\n\nCONFIG_ARGS="--quiet"\n',
        '%build\n\n'
        'BUILD_ANNOBIN_GCC_PLUGIN_DIR=%{ANNOBIN_GCC_PLUGIN_DIR}\n'
        'if [ ! -f "${BUILD_ANNOBIN_GCC_PLUGIN_DIR}/include/bversion.h" ] && '
        '[ -f %{_sourcedir}/builddeps/devtoolset-14-gcc-plugin-devel/opt/rh/devtoolset-14/root/usr/lib/gcc/x86_64-redhat-linux/%{gcc_major}/plugin/include/bversion.h ]; then\n'
        '  BUILD_ANNOBIN_GCC_PLUGIN_DIR=%{_sourcedir}/builddeps/devtoolset-14-gcc-plugin-devel/opt/rh/devtoolset-14/root/usr/lib/gcc/x86_64-redhat-linux/%{gcc_major}/plugin\n'
        'fi\n\n'
        'CONFIG_ARGS="--quiet"\n',
        1,
    )
    text = text.replace(
        'CONFIG_ARGS="$CONFIG_ARGS --with-gcc-plugin-dir=%{ANNOBIN_GCC_PLUGIN_DIR}"',
        'CONFIG_ARGS="$CONFIG_ARGS --with-gcc-plugin-dir=${BUILD_ANNOBIN_GCC_PLUGIN_DIR}"',
        1,
    )
    text = text.replace(
        'export CFLAGS="$CFLAGS $RPM_OPT_FLAGS %build_cflags -I%{?_scl_root}/usr/include"\n'
        'export LDFLAGS="$LDFLAGS %build_ldflags -L%{?_scl_root}/usr/lib64 -L%{?_scl_root}/usr/lib"\n',
        'export CC=%gcc_for_annobin\n'
        'export CXX=%gxx_for_annobin\n'
        'export CFLAGS="$CFLAGS $RPM_OPT_FLAGS -I%{?_scl_root}/usr/include"\n'
        'export CXXFLAGS="$CXXFLAGS $RPM_OPT_FLAGS -I%{?_scl_root}/usr/include"\n'
        'export LDFLAGS="$LDFLAGS %{?__global_ldflags} -L%{?_scl_root}/usr/lib64 -L%{?_scl_root}/usr/lib"\n',
        1,
    )
    text = re.sub(
        r"%if %\{with plugin_rebuild\}\n# Rebuild the plugin\(s\), this time using the plugin itself!.*?%endif\n\n# endif for %%if \{with_plugin_rebuild\}\n%endif\n",
        "%if %{with plugin_rebuild}\n"
        "# Rebuild the plugin(s), this time using the plugin itself!  This\n"
        "# ensures that the plugin works, and that it contains annotations\n"
        "# of its own.\n\n"
        "%if %{with gccplugin}\n"
        "cp gcc-plugin/.libs/annobin.so.0.0.0 %{_tmppath}/tmp_annobin.so\n"
        "make -C gcc-plugin clean\n"
        "BUILD_FLAGS=\"-fplugin=%{_tmppath}/tmp_annobin.so\"\n\n"
        "# Disable the standard annobin plugin so that we do get conflicts.\n"
        "# Note: the \"-fplugin=annobin\" is here, despite the fact that it will also\n"
        "# be automatically added to the gcc command line via\n"
        "# \"-specs=/usr/lib/rpm/redhat/redhat-annobin-cc1\" because of a bug in gcc's\n"
        "# plugin command line options handling.\n"
        "BUILD_FLAGS=\"$BUILD_FLAGS -fplugin=annobin -fplugin-arg-annobin-disable\"\n\n"
        "# If building on RHEL7, enable the next option as the .attach_to_group\n"
        "# assembler pseudo op is not available in the assembler.\n"
        "BUILD_FLAGS=\"$BUILD_FLAGS -fplugin-arg-tmp_annobin-no-attach\"\n\n"
        "make -C gcc-plugin CXX=%gxx_for_annobin CXXFLAGS=\"%{optflags} $BUILD_FLAGS\"\n"
        "rm %{_tmppath}/tmp_annobin.so\n"
        "%endif\n\n"
        "%if %{with clangplugin}\n"
        "cp clang-plugin/annobin-for-clang.so %{_tmppath}/tmp_annobin.so\n"
        "make -C clang-plugin all CXXFLAGS=\"%{optflags} $BUILD_FLAGS\"\n"
        "%endif\n\n"
        "%if %{with llvmplugin}\n"
        "cp llvm-plugin/annobin-for-llvm.so %{_tmppath}/tmp_annobin.so\n"
        "make -C llvm-plugin all CXXFLAGS=\"%{optflags} $BUILD_FLAGS\"\n"
        "%endif\n\n"
        "%endif\n",
        text,
        flags=re.S,
        count=1,
    )
    text = text.replace(
        "# Also install a copy of the sources into the build tree.\n"
        "mkdir -p                            %{buildroot}%{annobin_source_dir}\n"
        "cp %{_sourcedir}/%{annobin_sources} %{buildroot}%{annobin_source_dir}/latest-annobin.tar.xz\n",
        "",
        1,
    )
    text = text.replace(
        "%dir %{annobin_source_dir}\n"
        "%{annobin_source_dir}/latest-annobin.tar.xz\n",
        "",
        1,
    )
    return text


def rewrite_binutils(text):
    text = rewrite_generic(text)
    for old, new in (
        ("%bcond_with bootstrap", "%bcond_without bootstrap"),
        ("%bcond_without gold", "%bcond_with gold"),
        ("%bcond_without debuginfod", "%bcond_with debuginfod"),
        ("%define bootstrapping 0", "%define bootstrapping 1"),
        ("%define gcc_package gcc", "%define gcc_package {}-gcc".format(TARGET_BOOTSTRAP_TOOLSET)),
        ("%define gxx_package gcc-c++", "%define gxx_package {}-gcc-c++".format(TARGET_BOOTSTRAP_TOOLSET)),
        ("%define gcc_for_binutils /usr/bin/gcc", "%define gcc_for_binutils {}/usr/bin/gcc".format(TARGET_BOOTSTRAP_PREFIX)),
        ("%define gxx_for_binutils /usr/bin/g++", "%define gxx_for_binutils {}/usr/bin/g++".format(TARGET_BOOTSTRAP_PREFIX)),
        ("BuildRequires: gcc-c++", "BuildRequires: {}-gcc-c++".format(TARGET_BOOTSTRAP_TOOLSET)),
    ):
        text = text.replace(old, new)
    info_cleanup = "\n\trm -f $local_infodir/{ctf-spec,sframe-spec}.info*\n"
    marker = "\n\trm -f $local_mandir/{dlltool,nlmconv,windres,windmc}*\n"
    if info_cleanup not in text and marker in text:
        text = text.replace(marker, marker + info_cleanup, 1)
    text = text.replace(
        "%if %{bootstrapping}\n"
        "%define alternatives_cmd     %{_sbindir}/alternatives\n"
        "%define alternatives_cmdline %{alternatives_cmd}\n"
        "%else\n"
        "%define alternatives_cmd     %{!?scl:%{_sbindir}}%{?scl:%{_root_sbindir}}/alternatives\n"
        "%define alternatives_cmdline %{alternatives_cmd}%{?scl: --altdir %{_sysconfdir}/alternatives --admindir %{_scl_root}/var/lib/alternatives}\n"
        "%endif\n",
        "%define alternatives_cmd     /usr/sbin/alternatives\n"
        "%define alternatives_cmdline %{alternatives_cmd}%{?scl: --altdir %{_sysconfdir}/alternatives --admindir %{_scl_root}/var/lib/alternatives}\n",
    )
    text = text.replace("%ldconfig_post\n", "/sbin/ldconfig\n")
    text = text.replace("%ldconfig_postun\n", "/sbin/ldconfig\n")
    return text


def rewrite_gdb(text):
    python3_scl_install_post = (
        "%global __os_install_post %{expand:\n"
        "    /usr/lib/rpm/brp-scl-compress %{_scl_root}\n"
        "    %{!?__debug_package:/usr/lib/rpm/brp-strip %{__strip}\n"
        "    /usr/lib/rpm/brp-strip-comment-note %{__strip} %{__objdump}\n"
        "    }\n"
        "    /usr/lib/rpm/brp-strip-static-archive %{__strip}\n"
        "    /usr/lib/rpm/brp-scl-python-bytecompile %{__python3} %{?_python_bytecompile_errors_terminate_build} %{_scl_root}\n"
        "    /usr/lib/rpm/brp-python-hardlink\n"
        "    %{!?__jar_repack:/usr/lib/rpm/redhat/brp-java-repack-jars}\n"
        "%{nil}}"
    )
    text = rewrite_generic(text)
    text = text.replace("%global _without_python 1\n", "")
    text = text.replace(
        "%if 0%{?rhel:1} && 0%{?rhel} <= 7\n"
        "BuildRequires: python-devel%{buildisa}\n"
        "%global __python /usr/bin/python2\n"
        "%else\n"
        "%global __python %{__python3}\n"
        "BuildRequires: python3-devel%{buildisa}\n"
        "%endif\n",
        "%global __python %{__python3}\n"
        "BuildRequires: python3-devel%{buildisa}\n",
        1,
    )
    text = text.replace(python3_scl_install_post + "\n", "")
    text = text.replace(
        "%global _python_bytecompile_extra 0",
        "%global _python_bytecompile_extra 0\n" + python3_scl_install_post,
        1,
    )
    text = text.replace(
        "BuildRequires: %{?scl_prefix}gcc-c++",
        "BuildRequires: {}gcc-c++".format(TARGET_BOOTSTRAP_TOOLSET + "-"),
    )
    text = text.replace(
        "%{!?scl:\n"
        " %global pkg_name %{name}\n"
        " %global _root_prefix %{_prefix}\n"
        " %global _root_datadir %{_datadir}\n"
        " %global _root_libdir %{_libdir}\n"
        "}\n",
        "%{!?scl:\n"
        " %global pkg_name %{name}\n"
        " %global _root_prefix %{_prefix}\n"
        " %global _root_datadir %{_datadir}\n"
        " %global _root_libdir %{_libdir}\n"
        "}\n\n"
        + python3_scl_install_post
        + "\n",
        1,
    )
    text = text.replace("BuildRequires: boost-devel\n", "")
    text = text.replace("BuildRequires: source-highlight-devel\n", "")
    text = text.replace("BuildRequires: elfutils-debuginfod-client-devel\n", "")
    text = text.replace("BuildRequires: texinfo-tex\n", "")
    text = text.replace("BuildRequires: texlive-collection-latexrecommended\n", "")
    text = text.replace("%global have_libipt 0", "%global have_libipt 1", 2)
    text = text.replace("%global have_debuginfod 1", "%global have_debuginfod 0")
    text = text.replace(
        "%global use_scl_for_debuginfod 1", "%global use_scl_for_debuginfod 0"
    )
    text = re.sub(
        r"%if 0%\{\!?rhel:1\} \|\| 0%\{\?rhel\} > 7\n"
        r"BuildRequires: libbabeltrace-devel%\{buildisa\}\n"
        r"(?:    %if %\{defined use_guile\}\n"
        r"(?:        .*\n)*?"
        r"    %endif\n)?"
        r"%endif\n",
        "",
        text,
        count=1,
    )
    text = text.replace("BuildRequires: libbabeltrace-devel%{buildisa}\n", "")
    text = text.replace(
        "%if 0%{!?rhel:1} || 0%{?rhel} > 7\n"
        "\t--with-babeltrace\t\t\t\t\t\\\n"
        "%else\n"
        "\t--without-babeltrace\t\t\t\t\t\\\n"
        "%endif\n",
        "\t--without-babeltrace\t\t\t\t\t\\\n",
        1,
    )
    text = text.replace(
        "%make_build \\\n     -C gdb/doc {gdb,annotate}{.info,/index.html,.pdf} MAKEHTMLFLAGS=--no-split MAKEINFOFLAGS=--no-split V=1",
        "%make_build \\\n     -C gdb/doc {gdb,annotate}.info MAKEINFOFLAGS=--no-split V=1",
    )
    text = text.replace(
        "This package provides INFO, HTML and PDF user manual for GDB.",
        "This package provides the INFO user manual for GDB.",
    )
    text = text.replace("%doc %{gdb_build}/gdb/doc/{gdb,annotate}.{html,pdf}\n", "")
    text = text.replace(
        "rm -f $RPM_BUILD_ROOT%{_datadir}/gdb/system-gdbinit/elinos.py\n"
        "rm -f $RPM_BUILD_ROOT%{_datadir}/gdb/system-gdbinit/wrs-linux.py\n"
        "rmdir $RPM_BUILD_ROOT%{_datadir}/gdb/system-gdbinit\n",
        "rm -rf $RPM_BUILD_ROOT%{_datadir}/gdb/system-gdbinit\n",
        1,
    )
    text = text.replace(
        "for i in `find $RPM_BUILD_ROOT%{_datadir}/gdb -name \"*.py\"`; do\n",
        "rm -rf $RPM_BUILD_ROOT%{_datadir}/gdb/python/gdb/dap\n"
        "for i in `find $RPM_BUILD_ROOT%{_datadir}/gdb -name \"*.py\"`; do\n",
        1,
    )
    text = text.replace(
        " # -DPTUNIT:BOOL=ON has no effect on ctest.\n"
        " %cmake -DCMAKE_BUILD_TYPE=RelWithDebInfo \\\n"
        "\t-DPTUNIT:BOOL=OFF \\\n"
        "\t-DDEVBUILD:BOOL=ON \\\n"
        "\t-DBUILD_SHARED_LIBS=OFF \\\n"
        "\t../../libipt-%{libipt_version}\n",
        " # -DPTUNIT:BOOL=ON has no effect on ctest.\n"
        " CMAKE_BIN=$(command -v cmake || command -v cmake3)\n"
        " CTEST_BIN=$(command -v ctest || command -v ctest3)\n"
        " test -n \"$CMAKE_BIN\"\n"
        " test -n \"$CTEST_BIN\"\n"
        " \"$CMAKE_BIN\" -DCMAKE_BUILD_TYPE=RelWithDebInfo \\\n"
        "\t-DPTUNIT:BOOL=OFF \\\n"
        "\t-DDEVBUILD:BOOL=ON \\\n"
        "\t-DBUILD_SHARED_LIBS=OFF \\\n"
        "\t-DCMAKE_INSTALL_PREFIX=%{_prefix} \\\n"
        "\t-DCMAKE_INSTALL_LIBDIR=%{_libdir} \\\n"
        "\t-DCMAKE_INSTALL_INCLUDEDIR=%{_includedir} \\\n"
        "\t../../libipt-%{libipt_version}\n",
        1,
    )
    text = text.replace(
        " make VERBOSE=1 %{?_smp_mflags}\n ctest -V %{?_smp_mflags}\n make install DESTDIR=../libipt-%{libipt_version}-root\n",
        " make VERBOSE=1 %{?_smp_mflags}\n \"$CTEST_BIN\" -V %{?_smp_mflags}\n make install DESTDIR=../libipt-%{libipt_version}-root\n",
        1,
    )
    for old in (
        "# Populate CFLAGS, LDFLAGS, CC, CXX, etc.\n%set_build_flags\n",
        'cd %{gdb_build}$fprofile\n\nexport CFLAGS="$RPM_OPT_FLAGS %{?_with_asan:-fsanitize=address}"\n',
    ):
        if old in text and BOOTSTRAP_ENV_BLOCK not in text.split(old, 1)[0]:
            if old.startswith("# Populate"):
                new = "# Populate CFLAGS, LDFLAGS, CC, CXX, etc.\n%set_build_flags\n{}\n".format(
                    BOOTSTRAP_ENV_BLOCK.rstrip()
                )
            else:
                new = 'cd %{gdb_build}$fprofile\n\n{}\nexport CFLAGS="$RPM_OPT_FLAGS %{?_with_asan:-fsanitize=address}"\n'.format(
                    BOOTSTRAP_ENV_BLOCK.rstrip()
                )
            text = text.replace(old, new, 1)
    if "GDB_FULL_CONFIGURE_FLAGS" in text and "--disable-source-highlight" not in text.split(
        "GDB_FULL_CONFIGURE_FLAGS", 1
    )[1]:
        text = text.replace(
            '\t--enable-unit-tests"',
            '\t--enable-unit-tests \\\n\t--disable-source-highlight"',
            1,
        )
    return text


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--kind", choices=("generic", "gcc", "binutils", "gdb", "make", "elfutils", "annobin", "strace", "valgrind"), default="generic"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    source = args.input.read_text(encoding="utf-8")
    if args.kind == "gcc":
        rendered = rewrite_gcc(source)
    elif args.kind == "binutils":
        rendered = rewrite_binutils(source)
    elif args.kind == "gdb":
        rendered = rewrite_gdb(source)
    elif args.kind == "make":
        rendered = rewrite_make(source)
    elif args.kind == "elfutils":
        rendered = rewrite_elfutils(source)
    elif args.kind == "annobin":
        rendered = rewrite_annobin(source)
    elif args.kind == "strace":
        rendered = rewrite_strace(source)
    elif args.kind == "valgrind":
        rendered = rewrite_valgrind(source)
    else:
        rendered = rewrite_generic(source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
