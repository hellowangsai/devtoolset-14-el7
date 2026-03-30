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

GCC_MACRO_BLOCK = """\
%global devtoolset14_el7 1
%global devtoolset14_target x86_64-redhat-linux
%global devtoolset14_languages c,c++,fortran
%global devtoolset14_disable_multilib 1
%global devtoolset14_disable_tsan 1
%global devtoolset14_keep_asan 1
%global devtoolset14_keep_ubsan 1

"""
EL7_LIBSTDCXX_PATCH = "gcc14-libstdc++-compat-el7.patch"
EL7_LIBSTDCXX_PATCH_NUMBER = 1002
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
        ("build_liblsan", 0),
        ("build_libtsan", 0),
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
    text = strip_libgccjit(text)
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
        "--kind", choices=("generic", "gcc", "binutils", "gdb"), default="generic"
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
    else:
        rendered = rewrite_generic(source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
