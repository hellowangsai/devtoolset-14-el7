# devtoolset-14 for CentOS 7

This repository scaffolds an EL7-style `devtoolset-14` using Rocky Linux 8
`gcc-toolset-14` source RPMs as the upstream source of truth for GCC 14,
binutils, GDB, annobin, and dwz.

The bootstrap compiler used for local compile verification is `devtoolset-11`.

The implementation is intentionally split into two layers:

1. Upstream import:
   - discover and download the latest Rocky 8 `gcc-toolset-14` source RPMs
   - extract the upstream spec files and sources
2. EL7 backport overlay:
   - render EL7-friendly SCL meta packages for `devtoolset-14`
   - rewrite the upstream specs from `gcc-toolset-14` to `devtoolset-14`
   - force EL7-oriented defaults: `x86_64`, `--disable-multilib`,
     sanitizer-first, and no `TSan` in the first phase

## What is implemented here

- source discovery from Rocky 8 `Devel/source/tree`
- download and extract helpers for source RPMs
- SCL meta package templates:
  - `devtoolset-14-runtime`
  - `devtoolset-14`
  - `devtoolset-14-toolchain`
- a spec rewriter for upstream `gcc-toolset-14` specs
- sanitizer smoke tests for `ASan` and `UBSan`
- overlap smoke tests for locale, exceptions, futures, and thread primitives
- a libstdc++ model verifier that enforces the `devtoolset-11`-style
  linker-script-plus-nonshared layout
- a baseline analyzer for comparing CentOS 7 `devtoolset-8`,
  local `devtoolset-11`, and Rocky 8 `gcc-toolset-14`
- an EL7 overlay patch generator for GCC 14 `libstdc++_nonshared48`

## Current source scope

The Rocky 8 toolset components wired into the fetch pipeline are:

- `gcc-toolset-14`
- `gcc-toolset-14-annobin`
- `gcc-toolset-14-binutils`
- `gcc-toolset-14-dwz`
- `gcc-toolset-14-gcc`
- `gcc-toolset-14-gdb`

`ASan` and `UBSan` runtime packages are expected to come from the rewritten GCC
spec, because Rocky exposes them as GCC subpackages rather than standalone SRPMs.

## Quick start

```bash
make sources
make extract
make render-scl
make rewrite-fixtures
make stage-rpmbuild
make verify-bootstrap
make verify-libstdcxx
make generate-el7-libstdcxx-patch
make download-centos7-source
make extract-centos7-source
make download-centos7-libstdcxx
make extract-centos7-libstdcxx
make download-rocky8-libstdcxx
make extract-rocky8-libstdcxx
make analyze-libstdcxx
make test
```

To rewrite extracted upstream specs after `make extract`:

```bash
scripts/rewrite_extracted_specs.sh vendor/extracted build/generated/SPECS
```

To stage rewritten specs and extracted sources into an `rpmbuild` tree:

```bash
scripts/prepare_rpmbuild_tree.sh
```

To validate sanitizers after the RPMs are built and installed:

```bash
scripts/check_sanitizers.sh devtoolset-14
```

To validate the main overlap-sensitive symbol families after the RPMs are built
and installed:

```bash
make overlap-smoke
```

Or run it directly and override the legacy producer toolset used by the
mixed-ABI static-library smoke:

```bash
scripts/check_overlap_smoke.sh devtoolset-14 devtoolset-11
```

To validate the `elfutils` toolchain pieces after the RPMs are built and
installed:

```bash
make check-elfutils
```

Or run it directly:

```bash
scripts/check_elfutils_smoke.sh devtoolset-14
```

For in-tree verification before rebuilding RPMs, the script also supports
overriding the nonshared archive and adding explicit compiler flags:

```bash
EXTRA_CXXFLAGS='-D_GLIBCXX_USE_CXX11_ABI=0' \
NONSHARED_ARCHIVE_OVERRIDE=build/rpmbuild/BUILD/gcc-*/obj-x86_64-redhat-linux/x86_64-redhat-linux/libstdc++-v3/src/.libs/libstdc++_nonshared48.a \
scripts/check_overlap_smoke.sh devtoolset-14 devtoolset-11
```

To produce a baseline report for `libstdc++_nonshared.a`:

```bash
make analyze-libstdcxx
```

To synthesize the EL7 overlay patch for GCC 14:

```bash
make generate-el7-libstdcxx-patch
```

To sync the generated EL7 overlay sources into the current prepared GCC source
tree without restarting the full RPM build:

```bash
make sync-el7-libstdcxx-overlay
```

To incrementally rebuild only the `libstdc++_nonshared48` pieces and rerun the
compatibility link check:

```bash
make quick-libstdcxx-check
```

If the generated overlay changed, refresh the prepared source tree first and
then run the incremental check in one step:

```bash
make quick-libstdcxx-check-refresh
```

The generated patch is written to:

- `build/generated/PATCHES/gcc14-libstdc++-compat-el7.patch`

The report is written to:

- `build/analysis/libstdcxx-nonshared.md`
- `build/analysis/libstdcxx-nonshared.json`

## Notes

- The generated meta packages do not replace system `/usr/bin/gcc` or system
  `libstdc++`.
- `libstdc++` is required to follow the `devtoolset-11` model:
  no private SCL `libstdc++.so.6`, no fallback to a full SCL runtime copy,
  and only a `libstdc++.so` linker script plus `libstdc++_nonshared.a`.
- The nonshared baseline analysis is intended to prove whether an EL7
  `nonshared48` target still needs to be built explicitly. It is not treated as
  safe to union the EL7 and EL8 nonshared archives.
- The current EL7 overlay is generated from Rocky 8 GCC 14 sources plus
  CentOS 7 `devtoolset-11` compatibility wrappers. It is meant to seed the
  backport and still needs end-to-end binary build validation.
- The quick libstdc++ check reuses an already prepared GCC build tree. It is
  the preferred loop for fixing `libstdc++_nonshared48` compile or link issues
  before retrying `rpmbuild -ba`.
- The SCL entry point remains `scl enable devtoolset-14 bash`.
- The first phase explicitly targets `ASan` and `UBSan`. `TSan` is disabled in
  the spec rewrite path because it is the highest-risk sanitizer on EL7.
