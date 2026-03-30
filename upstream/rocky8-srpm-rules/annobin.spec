
%{?scl_package:%global scl gcc-toolset-14}
%global scl_prefix gcc-toolset-14-
BuildRequires: scl-utils-build

%global __python /usr/bin/python3
%{?scl:%scl_package annobin}

Name:    %{?scl_prefix}annobin
Summary: Annotate and examine compiled binary files
Version: 12.88
Release: 1%{?dist}
License: GPL-3.0-or-later AND LGPL-2.0-or-later AND (GPL-2.0-or-later WITH GCC-exception-2.0) AND (LGPL-2.0-or-later WITH GCC-exception-2.0) AND GFDL-1.3-or-later
URL: https://sourceware.org/annobin/
# Maintainer: nickc@redhat.com
# Web Page: https://sourceware.org/annobin/
# Watermark Protocol: https://fedoraproject.org/wiki/Toolchain/Watermark

#---------------------------------------------------------------------------------

# Use "--without tests" to disable the testsuite.
%bcond_without tests

# Use "--without annocheck" to disable the installation of the annocheck program.
%bcond_without annocheck

# Use "--with debuginfod" to force support for debuginfod to be compiled into
# the annocheck program.  By default the configure script will check for
# availablilty at build time, but this might not match the run time situation.
# FIXME: Add a --without debuginfod option to forcefully disable the configure
# time check for debuginfod support.
%bcond_with debuginfod

# Use "--without clangplugin" to disable the building of the annobin plugin for Clang.
%bcond_without clangplugin

# Use "--without gccplugin" to disable the building of the annobin plugin for GCC.
%bcond_without gccplugin

# Use "--without llvmplugin" to disable the building of the annobin plugin for LLVM.
%bcond_without llvmplugin

# Set this to zero to disable the requirement for a specific version of gcc.
# This should only be needed if there is some kind of problem with the version
# checking logic or when building on RHEL-7 or earlier.
#
# Update: now that we have gcc version checking support in redhat-rpm-config
# there is no longer a great need for a hard gcc version check here.  Not
# enabling this check greatly simplifies the process of installing a new major
# version of gcc into the buildroot.
%global with_hard_gcc_version_requirement 0

%bcond_without plugin_rebuild
# Allow the building of annobin without using annobin itself.
# This is because if we are bootstrapping a new build environment we can have
# a new version of gcc installed, but without a new of annobin installed.
# (i.e. we are building the new version of annobin to go with the new version
# of gcc).  If the *old* annobin plugin is used whilst building this new
# version, the old plugin will complain that version of gcc for which it
# was built is different from the version of gcc that is now being used, and
# then it will abort.
#
# The default is to use plugin during rebuilds (cf BZ 1630550) but this can
# be changed because of the need to be able to rebuild annobin when a change
# to gcc breaks the version installed into the buildroot.  Note however that
# uncommenting the lines below will result in annocheck not passing the rpminspect
# tests....
# %%if %%{without plugin_rebuild}
# %%undefine _annotated_build
# %%endif

#---------------------------------------------------------------------------------

# Bootstrapping: Set this to 1 to build annobin with the system gcc.
# Then once GTS-gcc is built and in the buildroot, reset this variable
# to 0, bump the NVR and rebuild GTS-annobin.
%define bootstrapping 0
# # FIXME: Temporary - use this to get the annobin plugin into the buildroot.
# %%undefine _annotated_build

#---------------------------------------------------------------------------------

%global annobin_sources annobin-%{version}.tar.xz
Source: https://nickc.fedorapeople.org/%{annobin_sources}
# For the latest sources use:  git clone git://sourceware.org/git/annobin.git

# Insert patches here, if needed.
Patch01: annobin-nop.patch
Patch02: annobin-tmp-default-to-using-group-attach.patch
%if %{bootstrapping}
Patch03: annobin-gcc-plugin-ignore-major-version-diffs.patch
%endif

# This is where a copy of the sources will be installed.
%global annobin_source_dir %{?_scl_root}/%{_usrsrc}/annobin

%if %{bootstrapping}

BuildRequires: gcc gcc-c++

%define gcc_for_annobin /usr/bin/gcc
%define gxx_for_annobin /usr/bin/g++

%else

BuildRequires: %{?scl_prefix}gcc
BuildRequires: %{?scl_prefix}gcc-c++
BuildRequires: %{?scl_prefix}annobin-plugin-gcc
%{?scl:BuildRequires:%scl_runtime}

%{?scl:Requires:%scl_runtime}
# We need the gcc-toolset-N version of gcc in order to run annobin, as otherwise the versions will not match.
%{?scl:Requires:%scl_require_package %{scl} gcc}

%define gcc_for_annobin %{?_scl_root}/usr/bin/gcc
%define gxx_for_annobin %{?_scl_root}/usr/bin/g++

%endif

#---------------------------------------------------------------------------------

# Make sure that the necessary sub-packages are built.

%if %{with gccplugin}
Requires: %{name}-plugin-gcc
%endif

%if %{with llvmplugin}
Requires: %{name}-plugin-llvm
%endif

%if %{with clangplugin}
Requires: %{name}-plugin-clang
%endif

#---------------------------------------------------------------------------------

%description
This package contains the tools needed to annotate binary files created by
compilers, and also the tools needed to examine those annotations.

%if %{with gccplugin}
One of the tools is a plugin for GCC that records information about the
security options that were in effect when the binary was compiled.

Note - the plugin is automatically enabled in gcc builds via flags
provided by the redhat-rpm-macros package.
%endif

%if %{with clangplugin}
One of the tools is a plugin for Clang that records information about the
security options that were in effect when the binary was compiled.
%endif

%if %{with llvmplugin}
One of the tools is a plugin for LLVM that records information about the
security options that were in effect when the binary was compiled.
%endif

%if %{with annocheck}
One of the tools is a security checker which analyses the notes present in
annotated files and reports on any missing security options.
%endif

#---------------------------------------------------------------------------

# Now that we have sub-packages for all of the plugins and for annocheck,
# there are no executables left to go into the "annobin" rpm.  But top-level
# packages cannot have "BuildArch: noarch" if sub-packages do have
# architecture requirements, and rpmlint generates an error if an
# architecture specific rpm does not contain any binaries.  So instead all of
# the documentation has been moved into an architecture neutral sub-package,
# and there no longer is a top level annobin rpm at all.

%package docs
Summary: Documentation and shell scripts for use with annobin
BuildArch: noarch
# The documentation uses pod2man...
BuildRequires: perl-interpreter perl-podlators gawk make sharutils

%description docs
Provides the documentation files and example shell scripts for use with annobin.

#----------------------------------------------------------------------------
%if %{with tests}

%package tests
Summary: Test scripts and binaries for checking the behaviour and output of the annobin plugin

Requires: %{name}-docs = %{version}-%{release}
BuildRequires: make sharutils

%if %{with debuginfod}
BuildRequires: elfutils-debuginfod-client-devel
%endif

%description tests
Provides a means to test the generation of annotated binaries and the parsing
of the resulting files.

%endif

#----------------------------------------------------------------------------
%if %{with annocheck}

%package annocheck
Summary: A tool for checking the security hardening status of binaries

BuildRequires: elfutils elfutils-devel elfutils-libelf-devel rpm-devel make
%if %{bootstrapping}
BuildRequires: gcc
%else
BuildRequires: %{?scl_prefix}gcc
%endif

%if %{with debuginfod}
BuildRequires: elfutils-debuginfod-client-devel
%endif

Requires: %{name}-docs = %{version}-%{release}
Requires: cpio rpm

%description annocheck
Installs the annocheck program which uses the notes generated by annobin to
check that the specified files were compiled with the correct security
hardening options.

%package libannocheck
Summary: A library for checking the security hardening status of binaries

BuildRequires: elfutils elfutils-devel elfutils-libelf-devel rpm-devel make
%if %{bootstrapping}
BuildRequires: gcc
%else
BuildRequires: %{?scl_prefix}gcc
%endif

%if %{with debuginfod}
BuildRequires: elfutils-debuginfod-client-devel
%endif

Requires: %{name}-docs = %{version}-%{release}

%description libannocheck
Installs the libannocheck library which uses the notes generated by the
annobin plugins to check that the specified files were compiled with the
correct security hardening options.

%endif

#----------------------------------------------------------------------------
%if %{with gccplugin}

%package plugin-gcc
Summary: annobin gcc plugin

Requires: %{name}-docs = %{version}-%{release}
%if %{bootstrapping}
BuildRequires: gcc-c++ gcc-plugin-devel
%else
BuildRequires: %{?scl_prefix}gcc-c++ %{?scl_prefix}gcc-plugin-devel
%endif

# [Stolen from gcc-python-plugin]
# GCC will only load plugins that were built against exactly that build of GCC
# We thus need to embed the exact GCC version as a requirement within the
# metadata.
#
# Define "gcc_vr", a variable to hold the VERSION-RELEASE string for the gcc
# we are being built against.
#
# Unfortunately, we can't simply run:
#   rpm -q --qf="%%{version}-%%{release}"
# to determine this, as there's no guarantee of a sane rpm database within
# the chroots created by our build system
#
# So we instead query the version from gcc's output.
#
# gcc.spec has:
#   Version: %%{gcc_version}
#   Release: %%{gcc_release}%%{?dist}
#   ...snip...
#   echo 'Red Hat %%{version}-%%{gcc_release}' > gcc/DEV-PHASE
#
# So, given this output:
#
#   $ gcc --version
#   gcc (GCC) 4.6.1 20110908 (Red Hat 4.6.1-9)
#   Copyright (C) 2011 Free Software Foundation, Inc.
#   This is free software; see the source for copying conditions.  There is NO
#   warranty; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# we can scrape out the "4.6.1" from the version line.
#
# The following implements the above:

%global gcc_vr %(%gcc_for_annobin --version | head -n 1 | sed -e 's|.*(Red\ Hat\ ||g' -e 's|)$||g')

# We need the major version of gcc.
%global gcc_major %(echo "%{gcc_vr}" | cut -f1 -d".")
%global gcc_next  %(v="%{gcc_major}"; echo $((++v)))

# Needed when building the srpm.
%if 0%{?gcc_major} == 0
%global gcc_major 0
%endif

# For a gcc plugin gcc is required.
%if %{bootstrapping}
Requires: gcc
%else
%if %{with_hard_gcc_version_requirement}
# BZ 1607430 - There is an exact requirement on the major version of gcc.
Requires: (%{?scl_prefix}gcc >= %{gcc_major} with %{?scl_prefix}gcc < %{gcc_next})
%else
Requires: %{?scl_prefix}gcc
%endif
%endif

# Information about the gcc plugin is recorded in this file.
%global aver annobin-plugin-version-info

%description plugin-gcc
Installs an annobin plugin that can be used by gcc.

%endif

#---------------------------------------------------------------------------------
%if %{with llvmplugin}

%package plugin-llvm
Summary: annobin llvm plugin

Requires: %{name}-docs = %{version}-%{release}
Requires: llvm-libs
Conflicts: %{name} <= 9.60-1
BuildRequires: clang clang-devel llvm llvm-devel compiler-rt

%description plugin-llvm
Installs an annobin plugin that can be used by LLVM tools.

%endif

#---------------------------------------------------------------------------------
%if %{with clangplugin}

%package plugin-clang
Summary: annobin clang plugin

Requires: %{name}-docs = %{version}-%{release}
Requires: llvm-libs
Conflicts: %{name} <= 9.60-1
BuildRequires: clang clang-devel llvm llvm-devel compiler-rt

%description plugin-clang
Installs an annobin plugin that can be used by Clang.

%endif

#---------------------------------------------------------------------------------

# Decide where the plugins will live.  Change if necessary.

%if %{bootstrapping}

# If we are bootstrapping then we will be using the system gcc.  But we do
# not want to install the newly built GTS-14 annobin plugin into the system
# plugin directory.  So we hard code a path here.
# FIXME: This is going to need to be updated every time we bootstrap.  Find
# a better way.

%global GTS_GCC_MAJOR_VERSION 14

%global ANNOBIN_GCC_PLUGIN_DIR %{_scl_root}/usr/lib/gcc/%{_target_platform}/%{GTS_GCC_MAJOR_VERSION}/plugin

%else

%global ANNOBIN_GCC_PLUGIN_DIR %(%gcc_for_annobin --print-file-name=plugin)

%endif

%{!?llvm_plugin_dir:%global  llvm_plugin_dir  %{_libdir}/llvm/plugins}
%{!?clang_plugin_dir:%global clang_plugin_dir %{_libdir}/clang/plugins}

#---------------------------------------------------------------------------------

%prep
if [ -z "%{gcc_vr}" ]; then
    echo "*** Missing gcc_vr spec file macro, cannot continue." >&2
    exit 1
fi

echo "Requires: (%{?scl_prefix}gcc >= %{gcc_major} and %{?scl_prefix}gcc < %{gcc_next})"

# NB/ Do not add {?scl_prefix} to the -n option below.  The annobin sources
# unpack into a directory called annobin-VERSION not gcc-toolset-N-annobin-VERSION.
%autosetup -p1 -n annobin-%{version}

# The plugin has to be configured with the same arcane configure
# scripts used by gcc.  Hence we must not allow the Fedora build
# system to regenerate any of the configure files.
touch aclocal.m4 gcc-plugin/config.h.in
touch configure */configure Makefile.in */Makefile.in
# Similarly we do not want to rebuild the documentation.
touch doc/annobin.info

#---------------------------------------------------------------------------------

%build

CONFIG_ARGS="--quiet"

%if %{with debuginfod}
CONFIG_ARGS="$CONFIG_ARGS --with-debuginfod"
%else
# Note - we explicitly disable debuginfod support if it was not configured.
# This is because by default annobin's configue script will assume --with-debuginfod=auto
# and then run a build time test to see if debugingfod is available.  It
# may well be, but the build time environment may not match the run time
# environment, and the rpm will not have a Requirement on the debuginfod
# client.
CONFIG_ARGS="$CONFIG_ARGS --without-debuginfod"
%endif

%if %{without clangplugin}
CONFIG_ARGS="$CONFIG_ARGS --without-clang-plugin"
%endif

%if %{without gccplugin}
CONFIG_ARGS="$CONFIG_ARGS --without-gcc-plugin"
%else
CONFIG_ARGS="$CONFIG_ARGS --with-gcc-plugin-dir=%{ANNOBIN_GCC_PLUGIN_DIR}"
%endif

%if %{without llvmplugin}
CONFIG_ARGS="$CONFIG_ARGS --without-llvm-plugin"
%endif

%if %{without tests}
CONFIG_ARGS="$CONFIG_ARGS --without-tests"
%endif

%if %{without annocheck}
CONFIG_ARGS="$CONFIG_ARGS --without-annocheck"
%else
# Fedora and RHEL-10 support AArch64's -mbranch-protection=bti, RHEL-9 does not.
%if 0%{?fedora} != 0
export CFLAGS="$CFLAGS -DAARCH64_BRANCH_PROTECTION_SUPPORTED=1"
%endif
%endif

%set_build_flags

export CFLAGS="$CFLAGS $RPM_OPT_FLAGS %build_cflags -I%{?_scl_root}/usr/include"
export LDFLAGS="$LDFLAGS %build_ldflags -L%{?_scl_root}/usr/lib64 -L%{?_scl_root}/usr/lib"

# Set target-specific options to be used when building the Clang and LLVM plugins.
# FIXME: There should be a better way to do this.
%ifarch %{ix86} x86_64
export CLANG_TARGET_OPTIONS="-fcf-protection"
%endif

%ifarch aarch64
export CLANG_TARGET_OPTIONS="-mbranch-protection=standard"
%endif

%ifnarch riscv64
export CLANG_TARGET_OPTIONS="$CLANG_TARGET_OPTIONS -flto -O2"
%endif
	
# # Override the default fortification level used by the Clang and LLVM plugins.
# export PLUGIN_FORTIFY_OPTION="-D_FORTIFY_SOURCE=3"

CC=%gcc_for_annobin CXX=%gxx_for_annobin CFLAGS="$CFLAGS" LDFLAGS="$LDFLAGS" CXXFLAGS="$CFLAGS" %configure ${CONFIG_ARGS} || cat config.log

%make_build

%if %{with plugin_rebuild}
# Rebuild the plugin(s), this time using the plugin itself!  This
# ensures that the plugin works, and that it contains annotations
# of its own.

%if %{with gccplugin}
cp gcc-plugin/.libs/annobin.so.0.0.0 %{_tmppath}/tmp_annobin.so
make -C gcc-plugin clean
BUILD_FLAGS="-fplugin=%{_tmppath}/tmp_annobin.so"

# Disable the standard annobin plugin so that we do get conflicts.
# Note - rpm-4.10 uses a different way of evaluating macros.
%if 0%{?rhel} && 0%{?rhel} < 9
OPTS="$(rpm --eval '%undefine _annotated_build %build_cflags %build_ldflags')"
%else
OPTS="$(rpm --undefine=_annotated_build --eval '%build_cflags %build_ldflags')"
%endif

# If building on systems with an assembler that does not support the
# .attach_to_group pseudo op (eg RHEL-7) then enable the next line.
# BUILD_FLAGS="$BUILD_FLAGS -fplugin-arg-tmp_annobin-no-attach"

make -C gcc-plugin CXX=%gxx_for_annobin CXXFLAGS="$OPTS $BUILD_FLAGS"
rm %{_tmppath}/tmp_annobin.so
%endif

%if %{with clangplugin}
cp clang-plugin/annobin-for-clang.so %{_tmppath}/tmp_annobin.so
# To enable verbose more in the plugin append the following: ANNOBIN="verbose"
make -C clang-plugin clean all CLANG_TARGET_OPTIONS="$CLANG_TARGET_OPTIONS $BUILD_FLAGS" PLUGIN_INSTALL_DIR=%{clang_plugin_dir}
%endif

%if %{with llvmplugin}
cp llvm-plugin/annobin-for-llvm.so %{_tmppath}/tmp_annobin.so
# To enable verbose more in the plugin append the following: ANNOBIN_VERBOSE="true"
make -C llvm-plugin clean all CLANG_TARGET_OPTIONS="$CLANG_TARGET_OPTIONS $BUILD_FLAGS" PLUGIN_INSTALL_DIR=%{llvm_plugin_dir}
%endif

# endif for %%if {with_plugin_rebuild}
%endif

#---------------------------------------------------------------------------------

%install

# PLUGIN_INSTALL_DIR is used by the Clang and LLVM makefiles...
%make_install PLUGIN_INSTALL_DIR=%{buildroot}/%{llvm_plugin_dir}

%if %{with clangplugin}
# Move the clang plugin to a seperate directory.
mkdir -p %{buildroot}/%{clang_plugin_dir}
mv %{buildroot}/%{llvm_plugin_dir}/annobin-for-clang.so %{buildroot}/%{clang_plugin_dir}
%endif

%if %{with gccplugin}
pushd %{buildroot}/%{ANNOBIN_GCC_PLUGIN_DIR}

# Record the version of gcc that built this plugin.
# Note - we cannot just store %%{gcc_vr} as sometimes the gcc rpm version changes
# without the NVR being altered.  See BZ #2030671 for more discussion on this.
cat `%gcc_for_annobin --print-file-name=rpmver` > %{aver}

# Also rename the plugin to its GTS variant
mv annobin.so.0.0.0 gts-annobin.so.0.0.0
rm -f annobin.so annobin.so.0 gts-annobin.so gts-annobin.so.0
ln -s gts-annobin.so.0.0.0 gts-annobin.so
ln -s gts-annobin.so.0.0.0 gts-annobin.so.0

popd

# Also install a copy of the sources into the build tree.
mkdir -p                            %{buildroot}%{annobin_source_dir}
cp %{_sourcedir}/%{annobin_sources} %{buildroot}%{annobin_source_dir}/latest-annobin.tar.xz
%endif

rm -f %{buildroot}%{_infodir}/dir

# When annocheck is disabled, annocheck.1.gz will still be generated, remove it.
%if %{without annocheck}
rm -f %{_mandir}/man1/annocheck.1.gz
%endif

#---------------------------------------------------------------------------------

%if %{with tests}
%check
# The first "make check" is run with "|| :" so that we can capture any logs
# from failed tests.  The second "make check" is there so that the build
# will fail if any of the tests fail.
make check GCC=%gcc_for_annobin CC=%gcc_for_annobin || :
if [ -f tests/test-suite.log ]; then
    cat tests/test-suite.log
fi

# If necessary use uuencode to preserve test binaries here.  For example:
#   uuencode tests/tmp_atexit/atexit.strip atexit.strip

# Now repeat the tests so that we get the correct exit code.
make check GCC=%gcc_for_annobin CC=%gcc_for_annobin 
%endif

#---------------------------------------------------------------------------------

%files docs
%license COPYING3 LICENSE
%exclude %{_datadir}/doc/annobin-plugin/COPYING3
%exclude %{_datadir}/doc/annobin-plugin/LICENSE
%doc %{_datadir}/doc/annobin-plugin/annotation.proposal.txt
%{_infodir}/annobin.info*
%{_mandir}/man1/annobin.1*
%exclude %{_mandir}/man1/built-by.1*
%exclude %{_mandir}/man1/check-abi.1*
%exclude %{_mandir}/man1/hardened.1*
%exclude %{_mandir}/man1/run-on-binaries-in.1*

%if %{with llvmplugin}
%files plugin-llvm
%dir %{llvm_plugin_dir}
%{llvm_plugin_dir}/annobin-for-llvm.so
%endif

%if %{with clangplugin}
%files plugin-clang
%dir %{clang_plugin_dir}
%{clang_plugin_dir}/annobin-for-clang.so
%endif

%if %{with gccplugin}
%files plugin-gcc
%dir %{ANNOBIN_GCC_PLUGIN_DIR}

%{ANNOBIN_GCC_PLUGIN_DIR}/gts-annobin.so
%verify(owner) %{ANNOBIN_GCC_PLUGIN_DIR}/gts-annobin.so

%{ANNOBIN_GCC_PLUGIN_DIR}/gts-annobin.so.0
%verify(owner) %{ANNOBIN_GCC_PLUGIN_DIR}/gts-annobin.so.0

%{ANNOBIN_GCC_PLUGIN_DIR}/gts-annobin.so.0.0.0
%verify(owner) %{ANNOBIN_GCC_PLUGIN_DIR}/gts-annobin.so.0.0.0

%{ANNOBIN_GCC_PLUGIN_DIR}/%{aver}

%dir %{annobin_source_dir}
%{annobin_source_dir}/latest-annobin.tar.xz
%endif

%if %{with annocheck}
%files annocheck
%{_bindir}/annocheck
%{_mandir}/man1/annocheck.1*

%files libannocheck
%{_includedir}/libannocheck.h
%{_libdir}/libannocheck.*
%{_libdir}/pkgconfig/libannocheck.pc
%endif

#---------------------------------------------------------------------------------

%changelog
* Mon Feb 03 2025 Nick Clifton  <nickc@redhat.com> - 12.88-1
- Annocheck: Look for -fstack-clash-protection in DW_AT_producer string.  (RHEL-77142)

* Thu Aug 22 2024 Nick Clifton  <nickc@redhat.com> - 12.87-1
- Rebase for GTS 14.1 release.  (RHEL-76929)
- Annocheck: Fix locating string notes (again).  Add exception for glibc benchmark tests.  (RHEL-76456)
- Annocheck: Add crtoffloadtableS.o to list of known gcc binaries.  (RHEL-760404)
- Annocheck: Fix the --debug-dir option.
- Annocheck: Fix corrupt warning message when unable to locate separate debug info files.
- Annocheck: Remove spurious debugging messages.
- Annocheck: Always look for annobin notes in separate debug info files.  (RHEL-75778)
- Annocheck: Support multiple --debug-rpm and --debug-file options.  (RHEL-73349)
- Annocheck: Add support for sys-root'ed glibc packages.  (RHEL-71296)
- GCC Plugin: Tidy up use of gcc's diagnoatic headers.  (#32429)
- Testsuite: Use configured compiler when running tests.
- GCC Plugin: Fix building with gcc 15.  (#32429)
- Annocheck: Fix overly long debug messages.
- Annocheck: Rename rwx-seg test to load-segments.  Add more checks.  Add check for gaps as a future fail.
- Annocheck: Add --no-allow-excpetions to disable exceptions for known special binaries.
- Annocheck: Add --enable-future to enable future fail components in normal tests.
- Annocheck: Fix bug preventing the inclusion of the rpm name in reports.
- Annocheck: Add more exceptions for gcc binaries.  (RHEL-33365)
- Annocheck: Add --skip-passes option.
- Annocheck: Add exceptions for gcc binaries.  (RHEL-33365)
- Annocheck: Skip property note test for i386 binaries created by LLVM.  (#2323797)
- Annocheck: Skip FORTIFY and GLIBC_ASSERTIONS tests for LLVM produced binaries with unparseable DW_AT_producer attributes in their DWARF debug info.  (RHEL-65411)
- GCC Plugin: Change type of the .annobin.notes section from SHT_STRTAB to SHT_PROGBITS.

* Thu Aug 22 2024 Nick Clifton  <nickc@redhat.com> - 12.70-3
- NVR Bump to allow rebuilding with annotation.

* Tue Aug 13 2024 Nick Clifton  <nickc@redhat.com> - 12.70-2
- Clang & LLVM Plugins: Remove buildroot from plugin install directory.  (RHEL-54178)

* Tue Aug 13 2024 Nick Clifton  <nickc@redhat.com> - 12.70-1
- Clang & LLVM Plugins: Include install directory in binary.  (RHEL-54178)

* Mon Aug 12 2024 Nick Clifton  <nickc@redhat.com> - 12.69-1
- BuiltBy: Fix seg-fault when comparing language version strings.  (RHEL-53497)
- Spec File: Use correct names for the symlinks.  (RHEL-53210)

* Fri Aug 09 2024 Nick Clifton  <nickc@redhat.com> - 12.67-5
- Spec File: Use correct names for the symlinks.  (RHEL-53210)

* Thu Aug 08 2024 Nick Clifton  <nickc@redhat.com> - 12.67-4
- Spec File: Use correct names for the plugins.  (RHEL-53210)

* Thu Aug 08 2024 Nick Clifton  <nickc@redhat.com> - 12.67-3
- Spec File: Disable bootstrapping.

* Thu Aug 08 2024 Nick Clifton  <nickc@redhat.com> - 12.67-2
- Spec File: Use correct directory for plugin installation.  (RHEL-53210)
- Spec File: Disable plugin when running on wrong major version of the compiler.

* Wed Aug 07 2024 Nick Clifton  <nickc@redhat.com> - 12.67-1
- Annocheck: Stop spurious assembler warnings.  (RHEL-53213)
- Annocheck: Stop warnings about known gaps.    (RHEL-53218)
- Annocheck: Fix stack realign test.  (#2302427)

* Wed Aug 07 2024 Nick Clifton  <nickc@redhat.com> - 12.65-5
- Spec File: Change bootstrap gcc version to 14.  (RHEL-53210)

* Thu Aug 01 2024 Nick Clifton  <nickc@redhat.com> - 12.65-4
- Spec File: Remove scl-runtime requirement when bootstrapping.

* Thu Aug 01 2024 Nick Clifton  <nickc@redhat.com> - 12.65-3
- Spec File: Enable bootstrapping.

* Thu Aug 01 2024 Nick Clifton  <nickc@redhat.com> - 12.65-2
- Spec File: Remove spurious dash from install path of gcc plugin.  (RHEL-51183)

* Tue Jul 30 2024 Nick Clifton  <nickc@redhat.com> - 12.65-1
- Rebase to 12.65.  (RHEL-51056)
- Annocheck: Fix recording arguments for later re-use.  (RHEL-50802)
- GCC Plugin: Fix building AArch64 components with gcc earlier than 11.3.
- Annocheck: Add improvements to the builtby utility.
- Annocheck: Add support for ADA binaries.
- Annocheck: Add support for binaries built from more than two high level source languages.
- Annocheck: Add support for object files containing no executable code.
- Annocheck: Do not FAIL LLVM compiled binaries that have not been built with sanitize-cfi and/or sanitize-safe-stack.
- Annocheck: Add support for Fortran binaries.
- Annocheck: Add heuristic for detecting parts of the CGO runtime library.
- Annocheck: Add improvements for handling Clang runtime binaries.
- Annocheck: Add tweaks for mixed Rust/C binaries.  (#2284605)
- Annocheck: Add more glibc source file names.
- Annocheck: Skip GAPS test for GO binaries.  (RHEL-36308)
- Annocheck: Remove some false positives for Rust binaries.  (#2280239)
- Annocheck: Defer passing the branch protection test until all notes have been checked.
- GCC Plugin: Add extra code for detecting the branch protection setting.  (RHEL-35958)

* Fri Jul 26 2024 Nick Clifton  <nickc@redhat.com> - 12.52-5
- Spec File: Hard code the gcc plugin directory when boostrapping.  (RHEL-50148)

* Tue May 07 2024 Nick Clifton  <nickc@redhat.com> - 12.52-3
- Disable bootstrapping.  (RHEL-29850)

* Fri May 03 2024 Nick Clifton  <nickc@redhat.com> - 12.52-2
- Disable version checks in gcc plugin.  (RHEL-29850)

* Fri Apr 26 2024 Nick Clifton  <nickc@redhat.com> - 12.52-1
- Initial import of sources.
- Compared to GTS-13 annobin (12.32) the improvements are:
- Annocheck: Add OpenSSL Engine test.  (PTG-319)
- Annocheck: Test for gaps even when only one note is present.
- Annocheck: Skip AArch64 branch protection test for GO binaries.
- GCC Plugin: Disable active check for -Wimplicit-int for non-C sources.  (#2275884)
- Annocheck: Ignore stack checks for AMD GPU binaries.
- Annocheck: Do not produce FAIL result for i686 binaries in the RHEL-10 profile.
- Annocheck: Test for __stack_chk_guard being writeable.
- Annocheck: Update heuristics for detecting glibc code in executables.  (RHEL-30579)
- Clang & LLVM Plugins: Allow environment to override fortification level.  (RHEL-30579)
- Spec File: Override fortification level and set it to 3.
- Annocheck: Improve detection of -mbranch-protection option.
- Clang Plugin: Add global-file-syms option.
- LLVM Plugin: Add global-file-syms option.
- Plugins: Add support for ANNOBIN environment variable.
- GCC Plugin: Fix bug extracing the value of target specific command line options.
- Configure: Remove check for FrontendPluginRegistry.h header as it is stored in a non-standard location on Debian systems.
- Debuginfod test: Allow for the libdwfl library silently contacting the debuginfod server.
- LLVM Plugin: Use llvm-config to get the correct paths and options for building executables.
- Clang Plugin: Likewise.
- Enable silent rules for most building.
- Annocheck: Correctly extract DWARF attributes from DT_REL files.
- Annocheck: Improve heuristics for locating debug info files.  (#2267097)
- Configure: Harmonize configure options.    
- Clang Plugin: Fix building with Clang 18.  (#31414)
- GCC Plugin: Add support for MIPS specific target functions.
- GCC Plugin: Use .dc.a for address expressions in 64-bit ELF format notes.
- Spec File: Remove a workaround for ppc64le.
- Annocheck: Improve heuristic for skipping LTO and FORTIFY tests.  (#2264000)
- Annocheck: Also skip property note test for i686 binaries. (#2258571)
- Annocheck: Also skip the entry point test for i686 binaries. (#2258571)
- GCC Plugin: Do not use section groups with string format notes.
- Annocheck: Disable cf-protection test for i686 architecture. (#2258571)
- Spec File: Disable hard gcc check in order to allow builds with new version of gcc.
- Spec File: Do not install annocheck.1.gz when annocheck is disabled.
- Annocheck: Improve detection of FIPS compliant GO binaries.
- GCC Plugin: Fix recording of the -Wimplicit-int and -Wimplicit-function-declaration warnings.  Add active checks for when they are deliberately disabled.
- Tests: Fix implicit-values test so that it will compile with gcc 14+.

