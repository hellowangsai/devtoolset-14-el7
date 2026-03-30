%global __python /usr/bin/python3
%{?scl_package:%global scl gcc-toolset-14}
%global scl_prefix gcc-toolset-14-
BuildRequires: scl-utils-build
%{?scl:%scl_package gcc}
Summary: DWARF optimization and duplicate removal tool
Name: %{?scl_prefix}dwz
Version: 0.14
Release: 0%{?dist}
License: GPLv2+ and GPLv3+
# git archive --format=tar --remote=git://sourceware.org/git/dwz.git \
#   --prefix=dwz-%%{version}/ dwz-%%{version} \
#   | bzip2 -9 > dwz-%%{version}.tar.bz2
Source: dwz-%{version}.tar.xz
BuildRequires: gcc, gcc-c++, gdb, elfutils-libelf-devel, dejagnu
BuildRequires: make
%{?scl:Requires:%scl_runtime}

%description
The dwz package contains a program that attempts to optimize DWARF
debugging information contained in ELF shared libraries and ELF executables
for size, by replacing DWARF information representation with equivalent
smaller representation where possible and by reducing the amount of
duplication using techniques from DWARF standard appendix E - creating
DW_TAG_partial_unit compilation units (CUs) for duplicated information
and using DW_TAG_imported_unit to import it into each CU that needs it.

%prep
%setup -q -n dwz

%build
%make_build CFLAGS='%{optflags}' LDFLAGS='%{build_ldflags}' \
  prefix=%{_prefix} mandir=%{_mandir} bindir=%{_bindir}

%install
rm -rf %{buildroot}
%make_install prefix=%{_prefix} mandir=%{_mandir} bindir=%{_bindir}

%check
make check

%files
%license COPYING COPYING3 COPYING.RUNTIME
%{_bindir}/dwz
%{_mandir}/man1/dwz.1*

%changelog
* Mon Apr 29 2024 Marek Polacek <polacek@redhat.com> 0.14-0
- new package (RHEL-34755)
