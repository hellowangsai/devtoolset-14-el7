PYTHON ?= python3
ROOT := $(abspath .)
BUILD_DIR := $(ROOT)/build
SPECS_DIR := $(BUILD_DIR)/generated/SPECS
SRPM_DIR := $(ROOT)/vendor/srpms
EXTRACT_DIR := $(ROOT)/vendor/extracted
CENTOS7_SRPM_DIR := $(ROOT)/vendor/srpms-centos7
CENTOS7_RPM_DIR := $(ROOT)/vendor/rpms-centos7
ROCKY8_RPM_DIR := $(ROOT)/vendor/rpms-rocky8
ANALYSIS_DIR := $(BUILD_DIR)/analysis

.PHONY: sources extract render-scl rewrite-fixtures stage-rpmbuild verify-bootstrap verify-libstdcxx generate-el7-libstdcxx-patch sync-el7-libstdcxx-overlay quick-libstdcxx-check quick-libstdcxx-check-refresh overlap-smoke check-elfutils check-buildreqs download-centos7-source download-centos7-libstdcxx download-rocky8-libstdcxx extract-centos7-source extract-centos7-libstdcxx extract-rocky8-libstdcxx analyze-libstdcxx test check-sh clean

sources:
	$(ROOT)/scripts/download_rocky_sources.sh $(SRPM_DIR)

extract:
	$(ROOT)/scripts/extract_srpms.sh $(SRPM_DIR) $(EXTRACT_DIR)

render-scl:
	$(PYTHON) $(ROOT)/scripts/render_scl_specs.py --out $(SPECS_DIR)

rewrite-fixtures: render-scl
	mkdir -p $(SPECS_DIR)
	$(PYTHON) $(ROOT)/scripts/rewrite_scl_spec.py \
		--kind gcc \
		--input $(ROOT)/tests/fixtures/gcc-toolset-14-gcc.spec \
		--output $(SPECS_DIR)/devtoolset-14-gcc.spec
	$(PYTHON) $(ROOT)/scripts/rewrite_scl_spec.py \
		--kind generic \
		--input $(ROOT)/tests/fixtures/gcc-toolset-14-binutils.spec \
		--output $(SPECS_DIR)/devtoolset-14-binutils.spec

stage-rpmbuild:
	$(ROOT)/scripts/prepare_rpmbuild_tree.sh

verify-bootstrap:
	$(ROOT)/scripts/verify_bootstrap_toolchain.sh

verify-libstdcxx:
	$(ROOT)/scripts/rewrite_extracted_specs.sh $(ROOT)/vendor/extracted-core $(ROOT)/build/generated/CORE_SPECS
	$(ROOT)/scripts/verify_libstdcxx_model.sh

generate-el7-libstdcxx-patch:
	$(PYTHON) $(ROOT)/scripts/generate_gcc14_el7_libstdcxx_compat_patch.py

sync-el7-libstdcxx-overlay:
	BUILD_DIR=$$(find $(ROOT)/build/rpmbuild/BUILD -maxdepth 1 -mindepth 1 -type d -name 'gcc-*' | sort | tail -n 1); \
	test -n "$$BUILD_DIR"; \
	$(PYTHON) $(ROOT)/scripts/generate_gcc14_el7_libstdcxx_compat_patch.py \
		--sync-tree "$$BUILD_DIR" \
		--skip-output

quick-libstdcxx-check:
	$(ROOT)/scripts/check_libstdcxx_nonshared_build.sh

quick-libstdcxx-check-refresh:
	$(ROOT)/scripts/check_libstdcxx_nonshared_build.sh --refresh-overlay

overlap-smoke:
	$(ROOT)/scripts/check_overlap_smoke.sh

check-elfutils:
	$(ROOT)/scripts/check_elfutils_smoke.sh

check-buildreqs:
	$(ROOT)/scripts/check_build_prereqs.sh

download-centos7-source:
	$(ROOT)/scripts/download_yum_repo_packages.sh \
		$(CENTOS7_SRPM_DIR) \
		$(ROOT)/manifests/centos7-source-packages.txt \
		http://vault.centos.org/7.9.2009/sclo/Source/rh \
		src

download-centos7-libstdcxx:
	$(ROOT)/scripts/download_yum_repo_packages.sh \
		$(CENTOS7_RPM_DIR) \
		$(ROOT)/manifests/centos7-x86_64-packages.txt \
		http://linuxsoft.cern.ch/centos-vault/7.9.2009/sclo/x86_64/rh \
		x86_64

download-rocky8-libstdcxx:
	$(ROOT)/scripts/download_yum_repo_packages.sh \
		$(ROCKY8_RPM_DIR) \
		$(ROOT)/manifests/rocky8-appstream-libstdcxx-packages.txt \
		https://download.rockylinux.org/pub/rocky/8.10/AppStream/x86_64/os \
		x86_64

extract-centos7-source:
	$(ROOT)/scripts/extract_srpms.sh $(CENTOS7_SRPM_DIR) $(ROOT)/vendor/extracted-centos7

extract-centos7-libstdcxx:
	$(ROOT)/scripts/extract_rpms.sh $(CENTOS7_RPM_DIR) $(ROOT)/vendor/extracted-centos7-rpms

extract-rocky8-libstdcxx:
	$(ROOT)/scripts/extract_rpms.sh $(ROCKY8_RPM_DIR) $(ROOT)/vendor/extracted-rocky8-rpms

analyze-libstdcxx:
	$(PYTHON) $(ROOT)/scripts/analyze_libstdcxx_nonshared.py \
		--out-json $(ANALYSIS_DIR)/libstdcxx-nonshared.json \
		--out-md $(ANALYSIS_DIR)/libstdcxx-nonshared.md

test: check-sh
	$(PYTHON) -m unittest discover -s $(ROOT)/tests -p 'test_*.py'

check-sh:
	bash -n $(ROOT)/scripts/download_rocky_sources.sh
	bash -n $(ROOT)/scripts/extract_srpms.sh
	bash -n $(ROOT)/scripts/rewrite_extracted_specs.sh
	bash -n $(ROOT)/scripts/prepare_rpmbuild_tree.sh
	bash -n $(ROOT)/scripts/verify_bootstrap_toolchain.sh
	bash -n $(ROOT)/scripts/verify_libstdcxx_model.sh
	bash -n $(ROOT)/scripts/check_sanitizers.sh
	bash -n $(ROOT)/scripts/check_overlap_smoke.sh
	bash -n $(ROOT)/scripts/check_elfutils_smoke.sh
	bash -n $(ROOT)/scripts/check_build_prereqs.sh
	bash -n $(ROOT)/scripts/check_libstdcxx_nonshared_build.sh
	bash -n $(ROOT)/scripts/download_yum_repo_packages.sh
	bash -n $(ROOT)/scripts/extract_rpms.sh

clean:
	rm -rf $(BUILD_DIR)
