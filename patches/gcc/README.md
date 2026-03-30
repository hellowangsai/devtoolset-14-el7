# GCC patch queue

This directory is reserved for EL7-specific GCC 14 backport patches.

The current repository scaffolding does not ship speculative patch content.
Instead, it prepares the pipeline that will:

- import the Rocky 8 `gcc-toolset-14-gcc` SRPM
- rewrite the spec into `devtoolset-14-gcc.spec`
- carry targeted EL7 backport patches here

Expected first patches:

- sanitizer compatibility adjustments for `ASan` and `UBSan`
- explicit `TSan` disablement on EL7
- multilib disablement for first-stage `x86_64` builds
