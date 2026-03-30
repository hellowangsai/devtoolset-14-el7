#!/usr/bin/env python3
"""Generate an EL7 libstdc++ compatibility overlay for GCC 14."""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_GCC14_TARBALL = (
    ROOT
    / "vendor/extracted-core/gcc-toolset-14-gcc-14.2.1-11.el8_10/gcc-14.2.1-20250110.tar.xz"
)
DEFAULT_GCC14_COMPAT_PATCH = (
    ROOT
    / "vendor/extracted-core/gcc-toolset-14-gcc-14.2.1-11.el8_10/gcc14-libstdc++-compat.patch"
)
DEFAULT_DTS11_COMPAT_PATCH = (
    ROOT
    / "vendor/extracted-centos7/devtoolset-11-gcc-11.2.1-9.el7/gcc11-libstdc++-compat.patch"
)
DEFAULT_OUTPUT = ROOT / "build/generated/PATCHES/gcc14-libstdc++-compat-el7.patch"

REL_SRC = Path("libstdc++-v3/src")

PATCH_ENV = dict(os.environ, LC_ALL="C")

DTS11_SOURCE_MAP = {
    "nonshared98": [
        "char8_t-rtti.S",
        "c++locale.cc",
        "collate_members.cc",
        "float128.S",
        "istream-string.cc",
        "locale.cc",
        "messages_members.cc",
        "monetary_members.cc",
        "numeric_members.cc",
        "numeric_members_cow.cc",
        "eh_exception.cc",
        "eh_catch.cc",
        "misc-inst.cc",
        "snprintf_lite-inst.cc",
        "locale-inst.cc",
        "wlocale-inst.cc",
        "sstream-inst.cc",
        "int12848.S",
        "eh_alloc48.cc",
        "ios_failure48.cc",
    ],
    "nonshared11": [
        "bad_array_length.cc",
        "bad_array_new.cc",
        "codecvt.cc",
        "condition_variable.cc",
        "cow-shim_facets.cc",
        "cow-sstream-inst.cc",
        "cow-stdexcept.cc",
        "cow-string-inst48.cc",
        "cow-wstring-inst48.cc",
        "ctype.cc",
        "cxx11-hash_tr1.cc",
        "cxx11-ios_failure.cc",
        "cxx11-locale-inst.cc",
        "cxx11-shim_facets.cc",
        "cxx11-stdexcept.cc",
        "cxx11-wlocale-inst.cc",
        "debug.cc",
        "del_opa.cc",
        "del_opant.cc",
        "del_ops.cc",
        "del_opsa.cc",
        "del_opva.cc",
        "del_opvant.cc",
        "del_opvs.cc",
        "del_opvsa.cc",
        "eh_aux_runtime.cc",
        "eh_ptr.cc",
        "eh_terminate.cc",
        "eh_throw.cc",
        "ext11-inst.cc",
        "fstream-inst.cc",
        "functexcept48.cc",
        "futex.cc",
        "future48.cc",
        "ios-inst.cc",
        "ios.cc",
        "iostream-inst.cc",
        "istream-inst.cc",
        "limits.cc",
        "locale-inst-asm.S",
        "locale-inst.cc",
        "new_handler.cc",
        "new_opa.cc",
        "new_opant.cc",
        "new_opva.cc",
        "new_opvant.cc",
        "ostream-inst.cc",
        "random48.cc",
        "regex48.cc",
        "shared_ptr48.cc",
        "snprintf_lite.cc",
        "sso_string.cc",
        "sstream-inst.cc",
        "string-inst.cc",
        "string-io-inst.cc",
        "system_error48.cc",
        "thread48.cc",
        "wlocale-inst.cc",
        "wstring-inst.cc",
        "wstring-io-inst.cc",
    ],
    "nonshared17": [
        "floating_from_chars.cc",
        "floating_to_chars.cc",
        "fs_dir.cc",
        "fs_ops.cc",
        "fs_path.cc",
        "memory_resource.cc",
        "cow-fs_dir.cc",
        "cow-fs_ops.cc",
        "cow-fs_path.cc",
        "ostream-inst.cc",
        "string-inst.cc",
        "cow-string-inst.cc",
    ],
    "nonshared20": [
        "sstream-inst.cc",
    ],
}

ROCKY14_SUPPLEMENTS = {
    "nonshared98": ["extfloat.S", "ios_init.cc", "locale_facets.cc"],
    "nonshared11": ["basic_file.cc"],
    "nonshared17": ["eh_call.cc", "eh_terminate.cc"],
    "nonshared20": ["tzdb80.cc"],
}

RENAME_MAP = {
    REL_SRC / "nonshared98/ios_failure48.cc": REL_SRC / "nonshared98/ios_failure.cc",
}

CONTENT_REWRITES = {
    Path("libstdc++-v3/include/bits/atomic_base.h"): (
        (
            "#if __glibcxx_atomic_wait\n"
            "      _GLIBCXX_ALWAYS_INLINE void\n"
            "      wait(__int_type __old,\n"
            "\t  memory_order __m = memory_order_seq_cst) const noexcept\n"
            "      {\n"
            "\tstd::__atomic_wait_address_v(&_M_i, __old,\n"
            "\t\t\t   [__m, this] { return this->load(__m); });\n"
            "      }\n",
            "#if __glibcxx_atomic_wait\n"
            "#ifdef _GLIBCXX_NONSHARED_TZDB_80\n"
            "      void\n"
            "      wait(__int_type __old,\n"
            "\t  memory_order __m = memory_order_seq_cst) const noexcept;\n"
            "#else\n"
            "      _GLIBCXX_ALWAYS_INLINE void\n"
            "      wait(__int_type __old,\n"
            "\t  memory_order __m = memory_order_seq_cst) const noexcept\n"
            "      {\n"
            "\tstd::__atomic_wait_address_v(&_M_i, __old,\n"
            "\t\t\t   [__m, this] { return this->load(__m); });\n"
            "      }\n"
            "#endif\n",
        ),
    ),
    Path("libstdc++-v3/include/ext/concurrence.h"): (
        (
            "    ~__scoped_lock() throw()\n"
            "    { _M_device.unlock(); }\n",
            "#ifdef _GLIBCXX_NONSHARED_CXX98\n"
            "    ~__scoped_lock() throw();\n"
            "#else\n"
            "    ~__scoped_lock() throw()\n"
            "    { _M_device.unlock(); }\n"
            "#endif\n",
        ),
    ),
    Path("libstdc++-v3/include/std/future"): (
        (
            '  private:\n'
            '    explicit\n'
            '    future_error(error_code __ec)\n'
            '    : logic_error("std::future_error: " + __ec.message()), _M_code(__ec)\n'
            '    { }\n'
            '\n'
            '    friend void __throw_future_error(int);\n',
            '  private:\n'
            '    explicit\n'
            '#ifdef _GLIBCXX_NONSHARED_CXX11_48\n'
            '    future_error(error_code __ec);\n'
            '#else\n'
            '    future_error(error_code __ec)\n'
            '    : logic_error("std::future_error: " + __ec.message()), _M_code(__ec)\n'
            '    { }\n'
            '#endif\n'
            '\n'
            '    friend void __throw_future_error(int);\n',
        ),
    ),
    REL_SRC / "nonshared98/c++locale.cc": (
        (
            '#include "../c++98/c++locale.cc"',
            '#include "../../config/locale/gnu/c_locale.cc"\n'
            'namespace __gnu_cxx _GLIBCXX_VISIBILITY(default)\n'
            '{\n'
            '  __scoped_lock::~__scoped_lock() throw()\n'
            '  { _M_device.unlock(); }\n'
            '} // namespace __gnu_cxx',
        ),
        (
            '} // namespace __gnu_cxx\n'
            'asm (".hidden _ZNKSt8Catalogs6_M_getEi");',
            '} // namespace __gnu_cxx\n'
            'namespace std _GLIBCXX_VISIBILITY(default)\n'
            '{\n'
            '_GLIBCXX_BEGIN_NAMESPACE_VERSION\n'
            '\n'
            '  template<>\n'
            '    void\n'
            '    vector<Catalog_info*>::_M_realloc_append(Catalog_info* const& __x)\n'
            '    {\n'
            '      const size_type __len = _M_check_len(1u, "vector::_M_realloc_append");\n'
            '      if (__len <= 0)\n'
            '\t__builtin_unreachable ();\n'
            '      pointer __old_start = this->_M_impl._M_start;\n'
            '      pointer __old_finish = this->_M_impl._M_finish;\n'
            '      const size_type __elems = end() - begin();\n'
            '      pointer __new_start(this->_M_allocate(__len));\n'
            '      pointer __new_finish(__new_start);\n'
            '\n'
            '      struct _Guard\n'
            '      {\n'
            '\tpointer _M_storage;\n'
            '\tsize_type _M_len;\n'
            '\t_Tp_alloc_type& _M_alloc;\n'
            '\n'
            '\t_Guard(pointer __s, size_type __l, _Tp_alloc_type& __a)\n'
            '\t: _M_storage(__s), _M_len(__l), _M_alloc(__a)\n'
            '\t{ }\n'
            '\n'
            '\t~_Guard()\n'
            '\t{\n'
            '\t  if (_M_storage)\n'
            '\t    __gnu_cxx::__alloc_traits<_Tp_alloc_type>::deallocate(_M_alloc, _M_storage, _M_len);\n'
            '\t}\n'
            '\n'
            '      private:\n'
            '\t_Guard(const _Guard&);\n'
            '      };\n'
            '\n'
            '      {\n'
            '\t_Guard __guard(__new_start, __len, _M_impl);\n'
            '\t_Alloc_traits::construct(this->_M_impl, __new_start + __elems, __x);\n'
            '\n'
            '\tstruct _Guard_elts\n'
            '\t{\n'
            '\t  pointer _M_first, _M_last;\n'
            '\t  _Tp_alloc_type& _M_alloc;\n'
            '\n'
            '\t  _Guard_elts(pointer __elt, _Tp_alloc_type& __a)\n'
            '\t  : _M_first(__elt), _M_last(__elt + 1), _M_alloc(__a)\n'
            '\t  { }\n'
            '\n'
            '\t  ~_Guard_elts()\n'
            '\t  { std::_Destroy(_M_first, _M_last, _M_alloc); }\n'
            '\n'
            '\tprivate:\n'
            '\t  _Guard_elts(const _Guard_elts&);\n'
            '\t};\n'
            '\n'
            '\t_Guard_elts __guard_elts(__new_start + __elems, _M_impl);\n'
            '\t__new_finish = std::__uninitialized_move_if_noexcept_a(\n'
            '\t\t\t __old_start, __old_finish,\n'
            '\t\t\t __new_start, _M_get_Tp_allocator());\n'
            '\t++__new_finish;\n'
            '\t__guard_elts._M_first = __old_start;\n'
            '\t__guard_elts._M_last = __old_finish;\n'
            '\t__guard._M_storage = __old_start;\n'
            '\t__guard._M_len = this->_M_impl._M_end_of_storage - __old_start;\n'
            '      }\n'
            '\n'
            '      this->_M_impl._M_start = __new_start;\n'
            '      this->_M_impl._M_finish = __new_finish;\n'
            '      this->_M_impl._M_end_of_storage = __new_start + __len;\n'
            '    }\n'
            '\n'
            '_GLIBCXX_END_NAMESPACE_VERSION\n'
            '} // namespace std\n'
            'asm (".hidden _ZNSt6vectorIPSt12Catalog_infoSaIS1_EE17_M_realloc_appendERKS1_");\n'
            'asm (".hidden _ZNKSt8Catalogs6_M_getEi");',
        ),
        (
            'asm (".hidden _ZNSt6vectorIPSt12Catalog_infoSaIS1_EE17_M_realloc_insertEN9__gnu_cxx17__normal_iteratorIPS1_S3_EERKS1_");',
            '//asm (".hidden _ZNSt6vectorIPSt12Catalog_infoSaIS1_EE17_M_realloc_insertEN9__gnu_cxx17__normal_iteratorIPS1_S3_EERKS1_");',
        ),
    ),
    REL_SRC / "nonshared20/tzdb80.cc": (
        (
            '#include "../c++20/tzdb.cc"\n',
            '#define _GLIBCXX_NONSHARED_TZDB_80 1\n'
            '#include "../c++20/tzdb.cc"\n'
            'namespace std _GLIBCXX_VISIBILITY(default)\n'
            '{\n'
            '_GLIBCXX_BEGIN_NAMESPACE_VERSION\n'
            '\n'
            '  template<>\n'
            '    void\n'
            '    __atomic_base<int>::wait(__int_type __old,\n'
            '      memory_order __m) const noexcept\n'
            '    {\n'
            '      __detail::__enters_wait __w(&_M_i);\n'
            '      __w._M_do_wait_v(__old,\n'
            '             [__m, this] { return this->load(__m); });\n'
            '    }\n'
            '\n'
            '_GLIBCXX_END_NAMESPACE_VERSION\n'
            '} // namespace std\n'
            'asm (".hidden _ZNKSt13__atomic_baseIiE4waitEiSt12memory_order");\n',
        ),
        (
            'asm (".hidden _ZSt23__atomic_wait_address_vIiZNKSt13__atomic_baseIiE4waitEiSt12memory_orderEUlvE_EvPKT_S4_T0_");',
            '//asm (".hidden _ZSt23__atomic_wait_address_vIiZNKSt13__atomic_baseIiE4waitEiSt12memory_orderEUlvE_EvPKT_S4_T0_");',
        ),
    ),
    REL_SRC / "nonshared98/collate_members.cc": (
        (
            '#include "../c++98/collate_members.cc"',
            '#include "../../config/locale/gnu/collate_members.cc"',
        ),
    ),
    REL_SRC / "nonshared98/locale_facets.cc": (
        (
            '#define _GLIBCXX_NONSHARED_CXX11_80\n'
            '#include "../c++98/locale_facets.cc"',
            '#define _GLIBCXX_NONSHARED_CXX11\n'
            '#include "../c++98/locale_facets.cc"\n'
            'asm (".hidden _ZSt22__verify_grouping_implPKcmS0_m");',
        ),
    ),
    REL_SRC / "nonshared98/locale-inst.cc": (
        (
            '#ifndef C\n'
            '# define C char\n'
            '#endif\n',
            '#ifndef C\n'
            '# define C char\n'
            '# define _GLIBCXX_NONSHARED_LOCALE_CHAR 1\n'
            '#endif\n',
        ),
        (
            '}\n',
            '}\n'
            '#ifdef _GLIBCXX_NONSHARED_LOCALE_CHAR\n'
            'asm (".globl _ZNKSt8time_getIcSt19istreambuf_iteratorIcSt11char_traitsIcEEE21_M_extract_via_formatES3_S3_RSt8ios_baseRSt12_Ios_IostateP2tmPKcRSt16__time_get_state\\n"\n'
            '     ".type _ZNKSt8time_getIcSt19istreambuf_iteratorIcSt11char_traitsIcEEE21_M_extract_via_formatES3_S3_RSt8ios_baseRSt12_Ios_IostateP2tmPKcRSt16__time_get_state,@function\\n"\n'
            '     "_ZNKSt8time_getIcSt19istreambuf_iteratorIcSt11char_traitsIcEEE21_M_extract_via_formatES3_S3_RSt8ios_baseRSt12_Ios_IostateP2tmPKcRSt16__time_get_state:\\n"\n'
            '     "jmp _ZNKSt7__cxx118time_getIcSt19istreambuf_iteratorIcSt11char_traitsIcEEE21_M_extract_via_formatES4_S4_RSt8ios_baseRSt12_Ios_IostateP2tmPKcRSt16__time_get_state\\n"\n'
            '     ".size _ZNKSt8time_getIcSt19istreambuf_iteratorIcSt11char_traitsIcEEE21_M_extract_via_formatES3_S3_RSt8ios_baseRSt12_Ios_IostateP2tmPKcRSt16__time_get_state,.-_ZNKSt8time_getIcSt19istreambuf_iteratorIcSt11char_traitsIcEEE21_M_extract_via_formatES3_S3_RSt8ios_baseRSt12_Ios_IostateP2tmPKcRSt16__time_get_state");\n'
            '#endif\n',
        ),
    ),
    REL_SRC / "nonshared98/messages_members.cc": (
        (
            '#include "../c++98/messages_members.cc"',
            '#include "../../config/locale/gnu/messages_members.cc"',
        ),
    ),
    REL_SRC / "nonshared98/monetary_members.cc": (
        (
            '#include "../c++98/monetary_members.cc"',
            '#include "../../config/locale/gnu/monetary_members.cc"',
        ),
    ),
    REL_SRC / "nonshared98/numeric_members.cc": (
        (
            '#include "../c++98/numeric_members.cc"',
            '#include "../../config/locale/gnu/numeric_members.cc"',
        ),
    ),
    REL_SRC / "nonshared98/numeric_members_cow.cc": (
        (
            '#include "../c++98/numeric_members.cc"',
            '#include "../../config/locale/gnu/numeric_members.cc"',
        ),
    ),
    REL_SRC / "nonshared98/wlocale-inst.cc": (
        (
            '#include "locale-inst.cc"\n'
            '#endif\n',
            '#include "locale-inst.cc"\n'
            'asm (".globl _ZNKSt8time_getIwSt19istreambuf_iteratorIwSt11char_traitsIwEEE21_M_extract_via_formatES3_S3_RSt8ios_baseRSt12_Ios_IostateP2tmPKwRSt16__time_get_state\\n"\n'
            '     ".type _ZNKSt8time_getIwSt19istreambuf_iteratorIwSt11char_traitsIwEEE21_M_extract_via_formatES3_S3_RSt8ios_baseRSt12_Ios_IostateP2tmPKwRSt16__time_get_state,@function\\n"\n'
            '     "_ZNKSt8time_getIwSt19istreambuf_iteratorIwSt11char_traitsIwEEE21_M_extract_via_formatES3_S3_RSt8ios_baseRSt12_Ios_IostateP2tmPKwRSt16__time_get_state:\\n"\n'
            '     "jmp _ZNKSt7__cxx118time_getIwSt19istreambuf_iteratorIwSt11char_traitsIwEEE21_M_extract_via_formatES4_S4_RSt8ios_baseRSt12_Ios_IostateP2tmPKwRSt16__time_get_state\\n"\n'
            '     ".size _ZNKSt8time_getIwSt19istreambuf_iteratorIwSt11char_traitsIwEEE21_M_extract_via_formatES3_S3_RSt8ios_baseRSt12_Ios_IostateP2tmPKwRSt16__time_get_state,.-_ZNKSt8time_getIwSt19istreambuf_iteratorIwSt11char_traitsIwEEE21_M_extract_via_formatES3_S3_RSt8ios_baseRSt12_Ios_IostateP2tmPKwRSt16__time_get_state");\n'
            '#endif\n',
        ),
    ),
    REL_SRC / "nonshared11/random48.cc": (
        ('#include "random.cc"', '#include "../c++11/random.cc"'),
    ),
    REL_SRC / "nonshared11/cxx11-ios_failure.cc": (
        (
            '#include "../c++11/cxx11-ios_failure.cc"',
            '#define _GLIBCXX_NONSHARED_CXX11_EL7\n#include "../c++11/cxx11-ios_failure.cc"',
        ),
    ),
    REL_SRC / "nonshared11/future48.cc": (
        (
            '#define _GLIBCXX_NONSHARED_CXX11_48\n'
            '#include "../c++11/future.cc"\n'
            'asm (".hidden _ZNSt13__future_base13_State_baseV211_Make_ready6_S_runEPv");\n',
            '#define _GLIBCXX_NONSHARED_CXX11_48\n'
            '#include "../c++11/future.cc"\n'
            'namespace std _GLIBCXX_VISIBILITY(default)\n'
            '{\n'
            '_GLIBCXX_BEGIN_NAMESPACE_VERSION\n'
            '\n'
            '  future_error::future_error(error_code __ec)\n'
            '  : logic_error("std::future_error: " + __ec.message()), _M_code(__ec)\n'
            '  { }\n'
            '\n'
            '_GLIBCXX_END_NAMESPACE_VERSION\n'
            '} // namespace std\n'
            'asm (".hidden _ZNSt13__future_base13_State_baseV211_Make_ready6_S_runEPv");\n',
        ),
    ),
    REL_SRC / "nonshared17/fs_ops.cc": (
        (
            '#include "../c++17/fs_ops.cc"\n'
            'asm (".hidden _ZN9__gnu_cxx13stdio_filebufIcSt11char_traitsIcEED0Ev");\n',
            '#include "../c++17/fs_ops.cc"\n'
            'namespace std _GLIBCXX_VISIBILITY(default)\n'
            '{\n'
            '_GLIBCXX_BEGIN_NAMESPACE_VERSION\n'
            '\n'
            '  using __el7_fs_path_iter = _Deque_iterator<filesystem::path,\n'
            '                                           filesystem::path&,\n'
            '                                           filesystem::path*>;\n'
            '  using __el7_fs_path_deque = deque<filesystem::path>;\n'
            '\n'
            '  template __el7_fs_path_iter\n'
            '  move<__el7_fs_path_iter, __el7_fs_path_iter>(\n'
            '      __el7_fs_path_iter, __el7_fs_path_iter, __el7_fs_path_iter);\n'
            '\n'
            '  template __el7_fs_path_iter\n'
            '  move_backward<__el7_fs_path_iter, __el7_fs_path_iter>(\n'
            '      __el7_fs_path_iter, __el7_fs_path_iter, __el7_fs_path_iter);\n'
            '\n'
            '  template filesystem::path&\n'
            '  __el7_fs_path_deque::emplace_back<filesystem::path>(\n'
            '      filesystem::path&&);\n'
            '\n'
            '  template void\n'
            '  __el7_fs_path_deque::_M_push_back_aux<const filesystem::path&>(\n'
            '      const filesystem::path&);\n'
            '\n'
            '_GLIBCXX_END_NAMESPACE_VERSION\n'
            '} // namespace std\n'
            'asm (".hidden _ZN9__gnu_cxx13stdio_filebufIcSt11char_traitsIcEED0Ev");\n',
        ),
        (
            'asm (".hidden _ZSt8_DestroyISt15_Deque_iteratorINSt10filesystem7__cxx114pathERS3_PS3_EEvT_S7_");',
            '//asm (".hidden _ZSt8_DestroyISt15_Deque_iteratorINSt10filesystem7__cxx114pathERS3_PS3_EEvT_S7_");',
        ),
        (
            'asm (".hidden _ZSt13move_backwardISt15_Deque_iteratorINSt10filesystem7__cxx114pathERS3_PS3_ES6_ET0_T_S8_S7_");',
            '//asm (".hidden _ZSt13move_backwardISt15_Deque_iteratorINSt10filesystem7__cxx114pathERS3_PS3_ES6_ET0_T_S8_S7_");',
        ),
        (
            'asm (".hidden _ZSt4moveISt15_Deque_iteratorINSt10filesystem7__cxx114pathERS3_PS3_ES6_ET0_T_S8_S7_");',
            '//asm (".hidden _ZSt4moveISt15_Deque_iteratorINSt10filesystem7__cxx114pathERS3_PS3_ES6_ET0_T_S8_S7_");',
        ),
    ),
    REL_SRC / "nonshared17/fs_dir.cc": (
        (
            'asm (".hidden _ZNSt10filesystem7__cxx114pathC1INSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEES1_EERKT_NS1_6formatE");',
            '//asm (".hidden _ZNSt10filesystem7__cxx114pathC1INSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEES1_EERKT_NS1_6formatE");',
        ),
        (
            'asm (".hidden _ZNSt10filesystem7__cxx114pathC2INSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEES1_EERKT_NS1_6formatE");',
            '//asm (".hidden _ZNSt10filesystem7__cxx114pathC2INSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEES1_EERKT_NS1_6formatE");',
        ),
        (
            'asm (".hidden _ZNKSt10filesystem7__cxx114_Dir7currentEv");',
            '//asm (".hidden _ZNKSt10filesystem7__cxx114_Dir7currentEv");',
        ),
    ),
    REL_SRC / "nonshared17/fs_path.cc": (
        (
            'asm (".hidden _ZTIZNSt10filesystem7__cxx114path10_S_convertIwEEDaPKT_S5_E5_UCvt");',
            '//asm (".hidden _ZTIZNSt10filesystem7__cxx114path10_S_convertIwEEDaPKT_S5_E5_UCvt");',
        ),
        (
            'asm (".hidden _ZTSZNSt10filesystem7__cxx114path10_S_convertIwEEDaPKT_S5_E5_UCvt");',
            '//asm (".hidden _ZTSZNSt10filesystem7__cxx114path10_S_convertIwEEDaPKT_S5_E5_UCvt");',
        ),
        (
            'asm (".hidden _ZTVZNSt10filesystem7__cxx114path10_S_convertIwEEDaPKT_S5_E5_UCvt");',
            '//asm (".hidden _ZTVZNSt10filesystem7__cxx114path10_S_convertIwEEDaPKT_S5_E5_UCvt");',
        ),
        (
            'asm (".hidden _ZZNSt10filesystem7__cxx114path10_S_convertIwEEDaPKT_S5_EN5_UCvtD0Ev");',
            '//asm (".hidden _ZZNSt10filesystem7__cxx114path10_S_convertIwEEDaPKT_S5_EN5_UCvtD0Ev");',
        ),
        (
            'asm (".hidden _ZZNSt10filesystem7__cxx114path10_S_convertIwEEDaPKT_S5_EN5_UCvtD1Ev");',
            '//asm (".hidden _ZZNSt10filesystem7__cxx114path10_S_convertIwEEDaPKT_S5_EN5_UCvtD1Ev");',
        ),
        (
            'asm (".hidden _ZZNSt10filesystem7__cxx114path10_S_convertIwEEDaPKT_S5_EN5_UCvtD2Ev");',
            '//asm (".hidden _ZZNSt10filesystem7__cxx114path10_S_convertIwEEDaPKT_S5_EN5_UCvtD2Ev");',
        ),
    ),
    REL_SRC / "c++11/future.cc": (
        (
            '#if __has_cpp_attribute(clang::require_constant_initialization)\n'
            '#  define __constinit [[clang::require_constant_initialization]]\n'
            '#endif\n'
            '\n'
            'namespace\n'
            '{\n',
            '#if __has_cpp_attribute(clang::require_constant_initialization)\n'
            '#  define __constinit [[clang::require_constant_initialization]]\n'
            '#endif\n'
            '\n'
            '#ifndef _GLIBCXX_NONSHARED_CXX11_48\n'
            'namespace\n'
            '{\n',
        ),
        (
            '  __constinit constant_init future_category_instance{};\n'
            '}\n'
            '\n'
            'namespace std _GLIBCXX_VISIBILITY(default)\n'
            '{\n',
            '  __constinit constant_init future_category_instance{};\n'
            '}\n'
            '#endif\n'
            '\n'
            'namespace std _GLIBCXX_VISIBILITY(default)\n'
            '{\n',
        ),
        (
            '  const error_category& future_category() noexcept\n'
            '  { return future_category_instance.cat; }\n'
            '\n'
            '  future_error::~future_error() noexcept { }\n'
            '\n'
            '  const char*\n'
            '  future_error::what() const noexcept { return logic_error::what(); }\n',
            '#ifndef _GLIBCXX_NONSHARED_CXX11_48\n'
            '  const error_category& future_category() noexcept\n'
            '  { return future_category_instance.cat; }\n'
            '\n'
            '  future_error::~future_error() noexcept { }\n'
            '\n'
            '  const char*\n'
            '  future_error::what() const noexcept { return logic_error::what(); }\n'
            '#endif\n',
        ),
        (
            '#ifdef _GLIBCXX_HAS_GTHREADS\n'
            '  __future_base::_Result_base::_Result_base() = default;\n'
            '\n'
            '  __future_base::_Result_base::~_Result_base() = default;\n',
            '#ifdef _GLIBCXX_HAS_GTHREADS\n'
            '#ifndef _GLIBCXX_NONSHARED_CXX11_48\n'
            '  __future_base::_Result_base::_Result_base() = default;\n'
            '\n'
            '  __future_base::_Result_base::~_Result_base() = default;\n'
            '#endif\n',
        ),
    ),
    Path("libstdc++-v3/include/Makefile.am"): (
        (
            'if ENABLE_CXX11_ABI\n'
            'stamp-cxx11-abi:\n'
            '\techo 1 > stamp-cxx11-abi\n'
            'else\n'
            'stamp-cxx11-abi:\n'
            '\techo 0 > stamp-cxx11-abi\n'
            'endif\n',
            'if ENABLE_CXX11_ABI\n'
            'stamp-cxx11-abi:\n'
            '\techo 0 > stamp-cxx11-abi\n'
            'else\n'
            'stamp-cxx11-abi:\n'
            '\techo 0 > stamp-cxx11-abi\n'
            'endif\n',
        ),
    ),
    Path("libstdc++-v3/include/Makefile.in"): (
        (
            '@ENABLE_CXX11_ABI_TRUE@stamp-cxx11-abi:\n'
            '@ENABLE_CXX11_ABI_TRUE@\techo 1 > stamp-cxx11-abi\n'
            '@ENABLE_CXX11_ABI_FALSE@stamp-cxx11-abi:\n'
            '@ENABLE_CXX11_ABI_FALSE@\techo 0 > stamp-cxx11-abi\n',
            '@ENABLE_CXX11_ABI_TRUE@stamp-cxx11-abi:\n'
            '@ENABLE_CXX11_ABI_TRUE@\techo 0 > stamp-cxx11-abi\n'
            '@ENABLE_CXX11_ABI_FALSE@stamp-cxx11-abi:\n'
            '@ENABLE_CXX11_ABI_FALSE@\techo 0 > stamp-cxx11-abi\n',
        ),
    ),
    REL_SRC / "c++11/cxx11-ios_failure.cc": (
        (
            '#if ! _GLIBCXX_USE_DUAL_ABI\n'
            '# error This file should not be compiled for this configuration.\n'
            '#endif\n'
            '\n'
            'namespace std _GLIBCXX_VISIBILITY(default)\n'
            '{\n'
            '_GLIBCXX_BEGIN_NAMESPACE_VERSION\n',
            '#if ! _GLIBCXX_USE_DUAL_ABI\n'
            '# error This file should not be compiled for this configuration.\n'
            '#endif\n'
            '\n'
            '#ifdef _GLIBCXX_NONSHARED_CXX11_EL7\n'
            'namespace\n'
            '{\n'
            '  struct io_error_category final : std::error_category\n'
            '  {\n'
            '    const char*\n'
            '    name() const noexcept final\n'
            '    { return "iostream"; }\n'
            '\n'
            '    _GLIBCXX_DEFAULT_ABI_TAG\n'
            '    std::string\n'
            '    message(int __ec) const final\n'
            '    {\n'
            '      switch (std::io_errc(__ec))\n'
            '      {\n'
            '      case std::io_errc::stream:\n'
            '        return "iostream error";\n'
            '      default:\n'
            '        return "Unknown error";\n'
            '      }\n'
            '    }\n'
            '  };\n'
            '\n'
            '  const std::error_category&\n'
            '  __io_category_instance() noexcept\n'
            '  {\n'
            '    static io_error_category __cat;\n'
            '    return __cat;\n'
            '  }\n'
            '} // namespace\n'
            '#endif\n'
            '\n'
            'namespace std _GLIBCXX_VISIBILITY(default)\n'
            '{\n'
            '_GLIBCXX_BEGIN_NAMESPACE_VERSION\n'
            '\n'
            '#ifdef _GLIBCXX_NONSHARED_CXX11_EL7\n'
            '  const error_category&\n'
            '  iostream_category() noexcept\n'
            '  { return __io_category_instance(); }\n'
            '#endif\n',
        ),
        (
            '  ios_base::failure::failure(const char* __str, const error_code& __ec)\n'
            '  : system_error(__ec, __str) { }\n',
            '  ios_base::failure::failure(const char* __str, const error_code& __ec)\n'
            '  : system_error(__ec, std::string(__str)) { }\n',
        ),
        (
            '    __ios_failure(const char* s) : failure(s)\n',
            '    __ios_failure(const char* s) : failure(std::string(s))\n',
        ),
        (
            '    __ios_failure(const char* s, const error_code& e) : failure(s, e)\n',
            '    __ios_failure(const char* s, const error_code& e)\n'
            '    : failure(std::string(s), e)\n',
        ),
    ),
    REL_SRC / "c++11/condition_variable.cc": (
        (
            '  void\n'
            '  condition_variable::wait(unique_lock<mutex>& __lock)\n'
            '  {\n'
            '    _M_cond.wait(*__lock.mutex());\n'
            '  }\n'
            '\n',
            '',
        ),
        (
            '  void\n'
            '  condition_variable::wait(unique_lock<mutex>& __lock)\n'
            '  {\n'
            '    _M_cond.wait(*__lock.mutex());\n'
            '  }\n'
            '\n'
            '#ifndef _GLIBCXX_NONSHARED_CXX11\n'
            '  void\n'
            '  condition_variable::notify_one() noexcept\n',
            '#ifndef _GLIBCXX_NONSHARED_CXX11\n'
            '  void\n'
            '  condition_variable::notify_one() noexcept\n',
        ),
    ),
    REL_SRC / "c++11/random.cc": (
        (
            '  // Called by old ABI version of random_device::_M_init(const std::string&).\n'
            '  void\n'
            '  random_device::_M_init(const char* s, size_t len)\n'
            '  {\n'
            '    const std::string token(s, len);\n'
            '#ifdef USE_MT19937\n'
            '    _M_init_pretr1(token);\n'
            '#else\n'
            '    _M_init(token);\n'
            '#endif\n'
            '  }\n',
            '  // Called by old ABI version of random_device::_M_init(const std::string&).\n'
            '#ifndef _GLIBCXX_NONSHARED_CXX11_48\n'
            '  void\n'
            '  random_device::_M_init(const char* s, size_t len)\n'
            '  {\n'
            '    const std::string token(s, len);\n'
            '#ifdef USE_MT19937\n'
            '    _M_init_pretr1(token);\n'
            '#else\n'
            '    _M_init(token);\n'
            '#endif\n'
            '  }\n'
            '#endif\n',
        ),
        (
            '  // Only called by code compiled against old releases of libstdc++.\n'
            '  // Forward the call to _M_getval() and let it decide what to do.\n'
            '  random_device::result_type\n'
            '  random_device::_M_getval_pretr1()\n'
            '  { return _M_getval(); }\n',
            '  // Only called by code compiled against old releases of libstdc++.\n'
            '  // Forward the call to _M_getval() and let it decide what to do.\n'
            '#ifndef _GLIBCXX_NONSHARED_CXX11_48\n'
            '  random_device::result_type\n'
            '  random_device::_M_getval_pretr1()\n'
            '  { return _M_getval(); }\n'
            '#endif\n',
        ),
        (
            '  void\n'
            '  random_device::_M_fini()\n'
            '  {\n',
            '#ifndef _GLIBCXX_NONSHARED_CXX11_48\n'
            '  void\n'
            '  random_device::_M_fini()\n'
            '  {\n',
        ),
        (
            '  }\n'
            '\n'
            '  random_device::result_type\n'
            '  random_device::_M_getval()\n'
            '  {\n',
            '  }\n'
            '#endif\n'
            '\n'
            '#ifndef _GLIBCXX_NONSHARED_CXX11_48\n'
            '  random_device::result_type\n'
            '  random_device::_M_getval()\n'
            '  {\n',
        ),
        (
            '  }\n'
            '\n'
            '  // Only called by code compiled against old releases of libstdc++.\n',
            '  }\n'
            '#endif\n'
            '\n'
            '  // Only called by code compiled against old releases of libstdc++.\n',
        ),
    ),
    REL_SRC / "c++11/shared_ptr.cc": (
        (
            '#ifndef _GLIBCXX_NONSHARED_CXX11_80\n'
            '  bad_weak_ptr::~bad_weak_ptr() noexcept = default;\n',
            '#ifndef _GLIBCXX_NONSHARED_CXX11_80\n'
            '#ifndef _GLIBCXX_NONSHARED_CXX11_48\n'
            '  bad_weak_ptr::~bad_weak_ptr() noexcept = default;\n',
        ),
        (
            '#endif\n'
            '#endif\n'
            '\n'
            '  bool\n',
            '#endif\n'
            '#endif\n'
            '#endif\n'
            '\n'
            '  bool\n',
        ),
    ),
    REL_SRC / "c++11/thread.cc": (
        (
            '  thread::_State::~_State() = default;\n'
            '\n'
            '  void\n'
            '  thread::join()\n'
            '  {\n',
            '  thread::_State::~_State() = default;\n'
            '\n'
            '#ifndef _GLIBCXX_NONSHARED_CXX11_44\n'
            '  void\n'
            '  thread::join()\n'
            '  {\n',
        ),
        (
            '    _M_id = id();\n'
            '  }\n'
            '\n'
            '  void\n'
            '  thread::detach()\n'
            '  {\n',
            '    _M_id = id();\n'
            '  }\n'
            '#endif\n'
            '\n'
            '#ifndef _GLIBCXX_NONSHARED_CXX11_44\n'
            '  void\n'
            '  thread::detach()\n'
            '  {\n',
        ),
        (
            '    _M_id = id();\n'
            '  }\n'
            '\n'
            '  void\n'
            '  thread::_M_start_thread(_State_ptr state, void (*depend)())\n',
            '    _M_id = id();\n'
            '  }\n'
            '#endif\n'
            '\n'
            '  void\n'
            '  thread::_M_start_thread(_State_ptr state, void (*depend)())\n',
        ),
        (
            '#if _GLIBCXX_THREAD_ABI_COMPAT\n'
            '  void\n'
            '  thread::_M_start_thread(__shared_base_type __b)\n'
            '  {\n',
            '#if _GLIBCXX_THREAD_ABI_COMPAT\n'
            '#ifndef _GLIBCXX_NONSHARED_CXX11_44\n'
            '  void\n'
            '  thread::_M_start_thread(__shared_base_type __b)\n'
            '  {\n',
        ),
        (
            '    _M_start_thread(std::move(__b), nullptr);\n'
            '  }\n'
            '\n'
            '  void\n'
            '  thread::_M_start_thread(__shared_base_type __b, void (*depend)())\n',
            '    _M_start_thread(std::move(__b), nullptr);\n'
            '  }\n'
            '#endif\n'
            '\n'
            '  void\n'
            '  thread::_M_start_thread(__shared_base_type __b, void (*depend)())\n',
        ),
        (
            '  unsigned int\n'
            '  thread::hardware_concurrency() noexcept\n'
            '  {\n'
            '    int __n = _GLIBCXX_NPROCS;\n'
            '    if (__n < 0)\n'
            '      __n = 0;\n'
            '    return __n;\n'
            '  }\n',
            '#ifndef _GLIBCXX_NONSHARED_CXX11_48\n'
            '  unsigned int\n'
            '  thread::hardware_concurrency() noexcept\n'
            '  {\n'
            '    int __n = _GLIBCXX_NPROCS;\n'
            '    if (__n < 0)\n'
            '      __n = 0;\n'
            '    return __n;\n'
            '  }\n'
            '#endif\n',
        ),
        (
            'namespace this_thread\n'
            '{\n'
            '  void\n'
            '  __sleep_for(chrono::seconds __s, chrono::nanoseconds __ns)\n'
            '  {\n',
            'namespace this_thread\n'
            '{\n'
            '#ifndef _GLIBCXX_NONSHARED_CXX11_48\n'
            '  void\n'
            '  __sleep_for(chrono::seconds __s, chrono::nanoseconds __ns)\n'
            '  {\n',
        ),
        (
            '#endif\n'
            '  }\n'
            '}\n'
            '_GLIBCXX_END_NAMESPACE_VERSION\n'
            '} // namespace std\n'
            '#endif // ! NO_SLEEP\n',
            '#endif\n'
            '  }\n'
            '#endif\n'
            '}\n'
            '_GLIBCXX_END_NAMESPACE_VERSION\n'
            '} // namespace std\n'
            '#endif // ! NO_SLEEP\n',
        ),
    ),
    REL_SRC / "nonshared17/cow-fs_ops.cc": (
        ('asm (".hidden _ZNSs4swapERSs");', '//asm (".hidden _ZNSs4swapERSs");'),
    ),
    REL_SRC / "nonshared17/cow-fs_dir.cc": (
        (
            'asm (".hidden _ZNKSt10filesystem4_Dir7currentEv");',
            '//asm (".hidden _ZNKSt10filesystem4_Dir7currentEv");',
        ),
    ),
    REL_SRC / "nonshared17/memory_resource.cc": (
        (
            'asm (".hidden _ZNSt22__shared_mutex_pthread6unlockEv");',
            '//asm (".hidden _ZNSt22__shared_mutex_pthread6unlockEv");',
        ),
    ),
    REL_SRC / "nonshared17/cow-fs_path.cc": (
        (
            'asm (".hidden _ZNKSt10filesystem4path5_List5_Impl4copyEv");',
            '//asm (".hidden _ZNKSt10filesystem4path5_List5_Impl4copyEv");',
        ),
        ('asm (".hidden _ZNSs6insertEmPKcm");', '//asm (".hidden _ZNSs6insertEmPKcm");'),
        ('asm (".hidden _ZNSs6resizeEmc");', '//asm (".hidden _ZNSs6resizeEmc");'),
        ('asm (".hidden _ZNSs7reserveEm");', '//asm (".hidden _ZNSs7reserveEm");'),
        ('asm (".hidden _ZNSs9_M_mutateEmmm");', '//asm (".hidden _ZNSs9_M_mutateEmmm");'),
        ('asm (".hidden _ZNSsC1ERKSsmm");', '//asm (".hidden _ZNSsC1ERKSsmm");'),
        ('asm (".hidden _ZNSsC2ERKSsmm");', '//asm (".hidden _ZNSsC2ERKSsmm");'),
        ('asm (".hidden _ZNSs12_M_leak_hardEv");', '//asm (".hidden _ZNSs12_M_leak_hardEv");'),
        (
            'asm (".hidden _ZNSbIwSt11char_traitsIwESaIwEE6resizeEmw");',
            '//asm (".hidden _ZNSbIwSt11char_traitsIwESaIwEE6resizeEmw");',
        ),
        (
            'asm (".hidden _ZNSbIwSt11char_traitsIwESaIwEE7reserveEm");',
            '//asm (".hidden _ZNSbIwSt11char_traitsIwESaIwEE7reserveEm");',
        ),
        (
            'asm (".hidden _ZNSbIwSt11char_traitsIwESaIwEE9_M_mutateEmmm");',
            '//asm (".hidden _ZNSbIwSt11char_traitsIwESaIwEE9_M_mutateEmmm");',
        ),
        (
            'asm (".hidden _ZNSbIwSt11char_traitsIwESaIwEE12_M_leak_hardEv");',
            '//asm (".hidden _ZNSbIwSt11char_traitsIwESaIwEE12_M_leak_hardEv");',
        ),
        (
            'asm (".hidden _ZNSt10filesystem4path5_List5beginEv");',
            '//asm (".hidden _ZNSt10filesystem4path5_List5beginEv");',
        ),
        (
            'asm (".hidden _ZNSt10filesystem4path7_Parser4nextEv");',
            '//asm (".hidden _ZNSt10filesystem4path7_Parser4nextEv");',
        ),
        (
            'asm (".hidden _ZNSt10filesystem4pathD1Ev");',
            '//asm (".hidden _ZNSt10filesystem4pathD1Ev");',
        ),
        (
            'asm (".hidden _ZNSt10filesystem4pathD2Ev");',
            '//asm (".hidden _ZNSt10filesystem4pathD2Ev");',
        ),
        (
            'asm (".hidden _ZSt16__do_str_codecvtISbIwSt11char_traitsIwESaIwEEcSt7codecvtIwc11__mbstate_tES5_MS6_KFNSt12codecvt_base6resultERS5_PKcSB_RSB_PwSD_RSD_EEbPKT0_SJ_RT_RKT1_RT2_RmT3_");',
            '//asm (".hidden _ZSt16__do_str_codecvtISbIwSt11char_traitsIwESaIwEEcSt7codecvtIwc11__mbstate_tES5_MS6_KFNSt12codecvt_base6resultERS5_PKcSB_RSB_PwSD_RSD_EEbPKT0_SJ_RT_RKT1_RT2_RmT3_");',
        ),
    ),
}

SUPPORT_FILES = (
    REL_SRC / "nonshared98/int128.S",
)


def run(args, cwd=None, capture=False):
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        env=PATCH_ENV,
        check=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def extract_new_files(patch_path):
    files = {}
    current = None
    current_path = None
    capturing = False
    is_new_file = False
    with patch_path.open(encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            if line.startswith("--- "):
                if is_new_file and current_path is not None:
                    files[current_path] = "".join(current)
                current = []
                current_path = None
                capturing = False
                is_new_file = False
                continue
            if line.startswith("+++ "):
                path = line[4:].split("\t", 1)[0].split(" ", 1)[0]
                current_path = Path(path)
                continue
            if line.startswith("@@ "):
                capturing = True
                if "@@ -0,0 " in line:
                    is_new_file = True
                continue
            if not capturing or not is_new_file or current is None:
                continue
            if line.startswith("+"):
                current.append(line[1:] + "\n")
            elif line.startswith(" "):
                current.append(line[1:] + "\n")
            elif line.startswith("\\"):
                continue
            else:
                capturing = False
        if is_new_file and current_path is not None:
            files[current_path] = "".join(current)
    return files


def replace_once(text, old, new):
    if old not in text:
        raise RuntimeError("replacement anchor not found")
    return text.replace(old, new, 1)


def render_sources(items):
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return " \\\n\t".join(items)


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def dedupe_paths(paths):
    seen = set()
    unique = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique


def rewrite_source_content(rel, text):
    rewrites = CONTENT_REWRITES.get(rel)
    if not rewrites:
        return text
    for old, new in rewrites:
        if new and new in text:
            continue
        if old not in text:
            raise RuntimeError("missing expected content in {}".format(rel))
        text = text.replace(old, new, 1)
    return text


def apply_content_rewrites(target_root):
    changed = []
    for rel in CONTENT_REWRITES:
        target_file = target_root / rel
        if not target_file.exists():
            continue
        original = target_file.read_text(encoding="utf-8")
        rewritten = rewrite_source_content(rel, original)
        if rewritten != original:
            write_text(target_file, rewritten)
            changed.append(rel)
    return changed


def update_top_level_makefile(path):
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "noinst_LTLIBRARIES = libstdc++_nonshared80.la \\\n\t\t     libstdc++_nonshared110.la",
        "noinst_LTLIBRARIES = libstdc++_nonshared48.la \\\n\t\t     libstdc++_nonshared80.la \\\n\t\t     libstdc++_nonshared110.la",
    )
    block = """libstdc___nonshared48_la_SOURCES =\n\nlibstdc___nonshared48_la_LIBADD = \\\n\t$(top_builddir)/src/nonshared98/libnonshared98convenience48.la \\\n\t$(top_builddir)/src/nonshared11/libnonshared11convenience48.la \\\n\t$(top_builddir)/src/nonshared17/libnonshared17convenience48.la \\\n\t$(top_builddir)/src/nonshared20/libnonshared20convenience48.la\n\nlibstdc___nonshared48_la_DEPENDENCIES = \\\n\t$(top_builddir)/src/nonshared98/libnonshared98convenience48.la \\\n\t$(top_builddir)/src/nonshared11/libnonshared11convenience48.la \\\n\t$(top_builddir)/src/nonshared17/libnonshared17convenience48.la \\\n\t$(top_builddir)/src/nonshared20/libnonshared20convenience48.la\n\n"""
    text = replace_once(text, "libstdc___nonshared80_la_SOURCES =", block + "libstdc___nonshared80_la_SOURCES =")
    write_text(path, text)


def update_subdir_makefile(path, libname, source_items):
    text = path.read_text(encoding="utf-8")
    basename = path.parent.name
    text = re.sub(
        r"noinst_LTLIBRARIES = {}80\.la \\\n\s+{}110\.la".format(
            re.escape(libname), re.escape(libname)
        ),
        "noinst_LTLIBRARIES = {0}48.la \\\n\t\t     {0}80.la \\\n\t\t     {0}110.la".format(
            libname
        ),
        text,
        count=1,
    )
    assignment = "lib{0}48_la_SOURCES = {1}\n".format(
        libname.replace("lib", "", 1),
        render_sources(source_items),
    )
    marker = "{}80_la_SOURCES =".format(libname)
    text = replace_once(
        text,
        marker,
        assignment + "\n" + marker,
    )
    if basename == "nonshared11":
        special_rules = """# Use special rules for the C++14 sources so that the proper flags are passed.
del_ops.lo: del_ops.cc
\t$(LTCXXCOMPILE) -std=gnu++14 -Wno-sized-deallocation -c $<
del_opvs.lo: del_opvs.cc
\t$(LTCXXCOMPILE) -std=gnu++14 -Wno-sized-deallocation -c $<

# Use special rules for the C++17 sources so that the proper flags are passed.
new_opa.lo: new_opa.cc
\t$(LTCXXCOMPILE) -std=gnu++1z -c $<
new_opant.lo: new_opant.cc
\t$(LTCXXCOMPILE) -std=gnu++1z -c $<
new_opva.lo: new_opva.cc
\t$(LTCXXCOMPILE) -std=gnu++1z -c $<
new_opvant.lo: new_opvant.cc
\t$(LTCXXCOMPILE) -std=gnu++1z -c $<
del_opa.lo: del_opa.cc
\t$(LTCXXCOMPILE) -std=gnu++1z -c $<
del_opant.lo: del_opant.cc
\t$(LTCXXCOMPILE) -std=gnu++1z -c $<
del_opsa.lo: del_opsa.cc
\t$(LTCXXCOMPILE) -std=gnu++1z -c $<
del_opva.lo: del_opva.cc
\t$(LTCXXCOMPILE) -std=gnu++1z -c $<
del_opvant.lo: del_opvant.cc
\t$(LTCXXCOMPILE) -std=gnu++1z -c $<
del_opvsa.lo: del_opvsa.cc
\t$(LTCXXCOMPILE) -std=gnu++1z -c $<

"""
        if "del_opa.lo: del_opa.cc" not in text:
            text = replace_once(
                text,
                "# Use special rules for source files that require -fchar8_t.\n",
                special_rules + "# Use special rules for source files that require -fchar8_t.\n",
            )
        if "codecvt.lo: codecvt.cc" not in text:
            text = replace_once(
                text,
                "# Use special rules for source files that require -fchar8_t.\n",
                "# Use special rules for source files that require -fchar8_t.\n"
                "codecvt.lo: codecvt.cc\n"
                "\t$(LTCXXCOMPILE) -fchar8_t -c $<\n",
            )
    write_text(path, text)


def source_items_by_subdir():
    rendered = {}
    for subdir, dts11_items in DTS11_SOURCE_MAP.items():
        items = []
        if subdir in ("nonshared98", "nonshared11"):
            items.extend(ROCKY14_SUPPLEMENTS[subdir])
            items.extend(dts11_items)
        elif subdir == "nonshared17":
            items.extend(DTS11_SOURCE_MAP[subdir])
            items.extend(ROCKY14_SUPPLEMENTS[subdir])
        elif subdir == "nonshared20":
            items.extend(DTS11_SOURCE_MAP[subdir])
            items.extend(ROCKY14_SUPPLEMENTS[subdir])
        else:
            items.extend(dts11_items)
        rendered[subdir] = items
    return rendered


def copy_needed_sources(target_root, dts11_added_files):
    written = []
    source_map = source_items_by_subdir()
    for subdir, names in source_map.items():
        for name in names:
            rel = REL_SRC / subdir / name
            target_file = target_root / rel
            if target_file.exists():
                continue
            source_rel = RENAME_MAP.get(rel, rel)
            if source_rel not in dts11_added_files:
                if name in ROCKY14_SUPPLEMENTS.get(subdir, []):
                    continue
                raise RuntimeError("missing source in dts11 patch: {}".format(source_rel))
            write_text(target_file, rewrite_source_content(rel, dts11_added_files[source_rel]))
            written.append(rel)
    for rel in SUPPORT_FILES:
        target_file = target_root / rel
        if target_file.exists():
            continue
        if rel not in dts11_added_files:
            raise RuntimeError("missing support source in dts11 patch: {}".format(rel))
        write_text(target_file, rewrite_source_content(rel, dts11_added_files[rel]))
        written.append(rel)
    return written


def build_overlay_tree(gcc14_tarball, gcc14_patch, dts11_patch):
    dts11_added_files = extract_new_files(dts11_patch)
    workdir = Path(tempfile.mkdtemp(prefix="gcc14-el7-libstdcxx-"))
    base_root = workdir / "base"
    target_root = workdir / "target"
    try:
        with tarfile.open(str(gcc14_tarball), "r:xz") as archive:
            archive.extractall(str(base_root))
        source_root = next(base_root.iterdir())
        run(["patch", "-p0", "-i", str(gcc14_patch)], cwd=source_root)
        shutil.copytree(str(source_root), str(target_root))

        update_top_level_makefile(target_root / REL_SRC / "Makefile.am")
        update_subdir_makefile(
            target_root / REL_SRC / "nonshared98/Makefile.am",
            "libnonshared98convenience",
            source_items_by_subdir()["nonshared98"],
        )
        update_subdir_makefile(
            target_root / REL_SRC / "nonshared11/Makefile.am",
            "libnonshared11convenience",
            source_items_by_subdir()["nonshared11"],
        )
        update_subdir_makefile(
            target_root / REL_SRC / "nonshared17/Makefile.am",
            "libnonshared17convenience",
            source_items_by_subdir()["nonshared17"],
        )
        update_subdir_makefile(
            target_root / REL_SRC / "nonshared20/Makefile.am",
            "libnonshared20convenience",
            source_items_by_subdir()["nonshared20"],
        )

        added_files = copy_needed_sources(target_root, dts11_added_files)
        rewritten_files = apply_content_rewrites(target_root)

        run(["autoreconf", "-fi"], cwd=target_root / "libstdc++-v3")

        tracked = dedupe_paths([
            Path("libstdc++-v3/include/Makefile.am"),
            Path("libstdc++-v3/include/Makefile.in"),
            REL_SRC / "Makefile.am",
            REL_SRC / "Makefile.in",
            REL_SRC / "nonshared98/Makefile.am",
            REL_SRC / "nonshared98/Makefile.in",
            REL_SRC / "nonshared11/Makefile.am",
            REL_SRC / "nonshared11/Makefile.in",
            REL_SRC / "nonshared17/Makefile.am",
            REL_SRC / "nonshared17/Makefile.in",
            REL_SRC / "nonshared20/Makefile.am",
            REL_SRC / "nonshared20/Makefile.in",
        ] + added_files + rewritten_files)
        return workdir, source_root, target_root, tracked
    except Exception:
        shutil.rmtree(str(workdir), ignore_errors=True)
        raise


def diff_paths(base_root, target_root, tracked):
    chunks = []
    for rel in tracked:
        base_file = base_root / rel
        target_file = target_root / rel
        if not base_file.exists() and not target_file.exists():
            continue
        if not base_file.exists():
            proc = subprocess.run(
                [
                    "diff",
                    "-u",
                    "--label",
                    "/dev/null",
                    "--label",
                    str(rel),
                    "/dev/null",
                    str(target_file),
                ],
                env=PATCH_ENV,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        else:
            proc = subprocess.run(
                [
                    "diff",
                    "-u",
                    "--label",
                    str(rel),
                    "--label",
                    str(rel),
                    str(base_file),
                    str(target_file),
                ],
                env=PATCH_ENV,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        if proc.returncode not in (0, 1):
            raise RuntimeError(proc.stderr.decode("utf-8", errors="replace"))
        if proc.returncode == 1:
            chunks.append(proc.stdout.decode("utf-8", errors="replace"))
    return "".join(chunks)


def sync_overlay_tree(sync_root, overlay_root, tracked, include_build_system=False):
    sync_root = Path(sync_root)
    written = []
    for rel in tracked:
        if not include_build_system and rel.name in {"Makefile.am", "Makefile.in"}:
            continue
        source_file = overlay_root / rel
        if not source_file.exists():
            continue
        target_file = sync_root / rel
        source_text = source_file.read_text(encoding="utf-8")
        if target_file.exists() and target_file.read_text(encoding="utf-8") == source_text:
            continue
        write_text(target_file, source_text)
        written.append(rel)
    return written


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcc14-tarball", type=Path, default=DEFAULT_GCC14_TARBALL)
    parser.add_argument(
        "--gcc14-compat-patch", type=Path, default=DEFAULT_GCC14_COMPAT_PATCH
    )
    parser.add_argument("--dts11-compat-patch", type=Path, default=DEFAULT_DTS11_COMPAT_PATCH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sync-tree", type=Path)
    parser.add_argument("--sync-build-system", action="store_true")
    parser.add_argument("--skip-output", action="store_true")
    args = parser.parse_args(argv)

    if args.skip_output and args.sync_tree is None:
        parser.error("--skip-output requires --sync-tree")

    for path in (args.gcc14_tarball, args.gcc14_compat_patch, args.dts11_compat_patch):
        if not path.exists():
            raise SystemExit("missing required input: {}".format(path))

    workdir, base_root, target_root, tracked = build_overlay_tree(
        args.gcc14_tarball, args.gcc14_compat_patch, args.dts11_compat_patch
    )
    try:
        if args.sync_tree is not None:
            written = sync_overlay_tree(
                args.sync_tree,
                target_root,
                tracked,
                include_build_system=args.sync_build_system,
            )
            print(
                "synced {} file(s) into {}".format(
                    len(written), args.sync_tree
                )
            )

        if not args.skip_output:
            patch_text = diff_paths(base_root, target_root, tracked)
            if not patch_text.strip():
                raise SystemExit("generated patch is empty")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(patch_text, encoding="utf-8")
            print("wrote {}".format(args.output))
    finally:
        shutil.rmtree(str(workdir), ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
