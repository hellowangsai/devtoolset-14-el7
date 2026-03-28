Name: gcc-toolset-14-gcc
Version: 14.2.1
Release: 7.1%{?dist}
Summary: GCC for gcc-toolset-14
Patch1000: gcc14-libstdc++-compat.patch

%global _scl_prefix /opt/rh/gcc-toolset-14/root

%prep
%patch -P1000 -p0 -b .libstdc++-compat~

%build
../configure \
  --enable-languages=c,c++,objc,objc++,fortran,go \
  --enable-multilib \
  --enable-libsanitizer

%package -n gcc-toolset-14-libasan
Summary: AddressSanitizer runtime

%package -n gcc-toolset-14-libtsan
Summary: ThreadSanitizer runtime
