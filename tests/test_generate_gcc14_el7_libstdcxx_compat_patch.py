import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.generate_gcc14_el7_libstdcxx_compat_patch import (
    apply_content_rewrites,
    copy_needed_sources,
    dedupe_paths,
    render_sources,
    rewrite_source_content,
    sync_overlay_tree,
    source_items_by_subdir,
    update_subdir_makefile,
)


class GenerateEl7CompatPatchTest(unittest.TestCase):
    def test_render_sources_uses_automake_continuations(self):
        rendered = render_sources(["foo.cc", "bar.cc", "baz.cc"])
        self.assertEqual("foo.cc \\\n\tbar.cc \\\n\tbaz.cc", rendered)

    def test_source_items_keep_supplements_without_duplicates(self):
        items = source_items_by_subdir()
        self.assertEqual(
            ["extfloat.S", "ios_init.cc", "locale_facets.cc"],
            items["nonshared98"][:3],
        )
        self.assertEqual(1, items["nonshared98"].count("char8_t-rtti.S"))
        self.assertEqual(1, items["nonshared11"].count("basic_file.cc"))
        self.assertIn("tzdb80.cc", items["nonshared20"])

    def test_dedupe_paths_preserves_first_occurrence_order(self):
        paths = [
            Path("libstdc++-v3/src/nonshared98/c++locale.cc"),
            Path("libstdc++-v3/src/nonshared17/fs_ops.cc"),
            Path("libstdc++-v3/src/nonshared98/c++locale.cc"),
            Path("libstdc++-v3/src/nonshared17/fs_path.cc"),
            Path("libstdc++-v3/src/nonshared17/fs_ops.cc"),
        ]
        self.assertEqual(
            [
                Path("libstdc++-v3/src/nonshared98/c++locale.cc"),
                Path("libstdc++-v3/src/nonshared17/fs_ops.cc"),
                Path("libstdc++-v3/src/nonshared17/fs_path.cc"),
            ],
            dedupe_paths(paths),
        )

    def test_copy_needed_sources_skips_existing_target_files(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            existing = root / "libstdc++-v3/src/nonshared98/extfloat.S"
            existing.parent.mkdir(parents=True, exist_ok=True)
            existing.write_text("existing\n", encoding="utf-8")
            with patch(
                "scripts.generate_gcc14_el7_libstdcxx_compat_patch.source_items_by_subdir",
                return_value={
                    "nonshared98": [
                        "extfloat.S",
                        "char8_t-rtti.S",
                        "ios_failure48.cc",
                    ]
                },
            ):
                written = copy_needed_sources(
                    root,
                    {
                        Path("libstdc++-v3/src/nonshared98/char8_t-rtti.S"): "char8\n",
                        Path("libstdc++-v3/src/nonshared98/ios_failure.cc"): "ios\n",
                        Path("libstdc++-v3/src/nonshared98/int128.S"): "int128\n",
                    },
                )
            self.assertNotIn(Path("libstdc++-v3/src/nonshared98/extfloat.S"), written)
            self.assertEqual("existing\n", existing.read_text(encoding="utf-8"))
            copied = root / "libstdc++-v3/src/nonshared98/ios_failure48.cc"
            self.assertTrue(copied.exists())
            self.assertEqual("ios\n", copied.read_text(encoding="utf-8"))
            support = root / "libstdc++-v3/src/nonshared98/int128.S"
            self.assertTrue(support.exists())
            self.assertEqual("int128\n", support.read_text(encoding="utf-8"))

    def test_rewrite_source_content_retargets_generated_locale_sources(self):
        rewritten = rewrite_source_content(
            Path("libstdc++-v3/src/nonshared98/c++locale.cc"),
            '#define _GLIBCXX_NONSHARED_CXX98 1\n'
            '#include "../c++98/c++locale.cc"\n'
            'asm (".hidden _ZNKSt8Catalogs6_M_getEi");\n'
            'asm (".hidden _ZNSt6vectorIPSt12Catalog_infoSaIS1_EE17_M_realloc_insertEN9__gnu_cxx17__normal_iteratorIPS1_S3_EERKS1_");\n',
        )
        self.assertIn('#include "../../config/locale/gnu/c_locale.cc"', rewritten)
        self.assertNotIn('#include "../c++98/c++locale.cc"', rewritten)
        self.assertIn("namespace __gnu_cxx _GLIBCXX_VISIBILITY(default)", rewritten)
        self.assertIn("__scoped_lock::~__scoped_lock() throw()", rewritten)
        self.assertIn("{ _M_device.unlock(); }", rewritten)
        self.assertIn("vector<Catalog_info*>::_M_realloc_append(Catalog_info* const& __x)", rewritten)
        self.assertIn('asm (".hidden _ZNSt6vectorIPSt12Catalog_infoSaIS1_EE17_M_realloc_appendERKS1_");', rewritten)
        self.assertIn('//asm (".hidden _ZNSt6vectorIPSt12Catalog_infoSaIS1_EE17_M_realloc_insertEN9__gnu_cxx17__normal_iteratorIPS1_S3_EERKS1_");', rewritten)

    def test_rewrite_source_content_fixes_locale_facets_verify_grouping_for_el7(self):
        rewritten = rewrite_source_content(
            Path("libstdc++-v3/src/nonshared98/locale_facets.cc"),
            '#define _GLIBCXX_NONSHARED_CXX11_80\n'
            '#include "../c++98/locale_facets.cc"\n',
        )
        self.assertIn('#define _GLIBCXX_NONSHARED_CXX11\n', rewritten)
        self.assertNotIn('_GLIBCXX_NONSHARED_CXX11_80', rewritten)
        self.assertIn('asm (".hidden _ZSt22__verify_grouping_implPKcmS0_m");', rewritten)

    def test_rewrite_source_content_adds_old_abi_time_get_char_alias(self):
        rewritten = rewrite_source_content(
            Path("libstdc++-v3/src/nonshared98/locale-inst.cc"),
            '#include <locale>\n'
            '\n'
            '#ifndef C\n'
            '# define C char\n'
            '#endif\n'
            '\n'
            'namespace std _GLIBCXX_VISIBILITY(default)   \n'
            '{\n'
            '\n'
            '  typedef time_get<C> S;\n'
            '\n'
            '  template\n'
            '  S::iter_type S::_M_extract_wday_or_month(iter_type, iter_type, int&,\n'
            '\t\t\t\t\t   const C **, size_t, ios_base&,\n'
            '\t\t\t\t\t   ios_base::iostate&) const;\n'
            '\n'
            '}\n',
        )
        self.assertIn('# define _GLIBCXX_NONSHARED_LOCALE_CHAR 1', rewritten)
        self.assertIn(
            '_ZNKSt8time_getIcSt19istreambuf_iteratorIcSt11char_traitsIcEEE21_M_extract_via_formatES3_S3_RSt8ios_baseRSt12_Ios_IostateP2tmPKcRSt16__time_get_state',
            rewritten,
        )
        self.assertIn(
            '_ZNKSt7__cxx118time_getIcSt19istreambuf_iteratorIcSt11char_traitsIcEEE21_M_extract_via_formatES4_S4_RSt8ios_baseRSt12_Ios_IostateP2tmPKcRSt16__time_get_state',
            rewritten,
        )

    def test_rewrite_source_content_adds_old_abi_time_get_wchar_alias(self):
        rewritten = rewrite_source_content(
            Path("libstdc++-v3/src/nonshared98/wlocale-inst.cc"),
            '#include <bits/c++config.h>\n'
            '\n'
            '#ifdef _GLIBCXX_USE_WCHAR_T\n'
            '#define C wchar_t\n'
            '#include "locale-inst.cc"\n'
            '#endif\n',
        )
        self.assertIn(
            '_ZNKSt8time_getIwSt19istreambuf_iteratorIwSt11char_traitsIwEEE21_M_extract_via_formatES3_S3_RSt8ios_baseRSt12_Ios_IostateP2tmPKwRSt16__time_get_state',
            rewritten,
        )
        self.assertIn(
            '_ZNKSt7__cxx118time_getIwSt19istreambuf_iteratorIwSt11char_traitsIwEEE21_M_extract_via_formatES4_S4_RSt8ios_baseRSt12_Ios_IostateP2tmPKwRSt16__time_get_state',
            rewritten,
        )

    def test_rewrite_source_content_moves_atomic_wait_out_of_header(self):
        rewritten = rewrite_source_content(
            Path("libstdc++-v3/include/bits/atomic_base.h"),
            "#if __glibcxx_atomic_wait\n"
            "      _GLIBCXX_ALWAYS_INLINE void\n"
            "      wait(__int_type __old,\n"
            "\t  memory_order __m = memory_order_seq_cst) const noexcept\n"
            "      {\n"
            "\tstd::__atomic_wait_address_v(&_M_i, __old,\n"
            "\t\t\t   [__m, this] { return this->load(__m); });\n"
            "      }\n",
        )
        self.assertIn("#ifdef _GLIBCXX_NONSHARED_TZDB_80\n      void\n      wait(__int_type __old,", rewritten)
        self.assertIn("memory_order __m = memory_order_seq_cst) const noexcept;\n#else\n", rewritten)
        self.assertIn("_GLIBCXX_ALWAYS_INLINE void\n      wait(__int_type __old,", rewritten)

    def test_rewrite_source_content_moves_scoped_lock_dtor_out_of_header(self):
        rewritten = rewrite_source_content(
            Path("libstdc++-v3/include/ext/concurrence.h"),
            "    ~__scoped_lock() throw()\n"
            "    { _M_device.unlock(); }\n",
        )
        self.assertIn("#ifdef _GLIBCXX_NONSHARED_CXX98\n    ~__scoped_lock() throw();", rewritten)
        self.assertIn("#else\n    ~__scoped_lock() throw()\n    { _M_device.unlock(); }\n#endif\n", rewritten)

    def test_rewrite_source_content_adds_tzdb80_atomic_wait_definition(self):
        rewritten = rewrite_source_content(
            Path("libstdc++-v3/src/nonshared20/tzdb80.cc"),
            '#include "../c++20/tzdb.cc"\n'
            'asm (".hidden _ZSt23__atomic_wait_address_vIiZNKSt13__atomic_baseIiE4waitEiSt12memory_orderEUlvE_EvPKT_S4_T0_");\n'
            'asm (".hidden _ZNKSt6chrono9time_zone4nameEv");\n',
        )
        self.assertIn("#define _GLIBCXX_NONSHARED_TZDB_80 1\n#include \"../c++20/tzdb.cc\"\n", rewritten)
        self.assertIn("template<>\n    void\n    __atomic_base<int>::wait(__int_type __old,", rewritten)
        self.assertIn("__detail::__enters_wait __w(&_M_i);", rewritten)
        self.assertIn("__w._M_do_wait_v(__old,", rewritten)
        self.assertIn('asm (".hidden _ZNKSt13__atomic_baseIiE4waitEiSt12memory_order");\n', rewritten)
        self.assertIn('//asm (".hidden _ZSt23__atomic_wait_address_vIiZNKSt13__atomic_baseIiE4waitEiSt12memory_orderEUlvE_EvPKT_S4_T0_");', rewritten)
        self.assertIn('asm (".hidden _ZNKSt6chrono9time_zone4nameEv");\n', rewritten)

    def test_rewrite_source_content_retargets_random48_to_cxx11_source(self):
        rewritten = rewrite_source_content(
            Path("libstdc++-v3/src/nonshared11/random48.cc"),
            '#define _GLIBCXX_NONSHARED_CXX11_48\n#include "random.cc"\n',
        )
        self.assertIn('#include "../c++11/random.cc"', rewritten)
        self.assertNotIn('#include "random.cc"', rewritten)

    def test_rewrite_source_content_moves_future_error_ctor_out_of_header(self):
        original = "\n".join(
            [
                '  private:',
                '    explicit',
                '    future_error(error_code __ec)',
                '    : logic_error("std::future_error: " + __ec.message()), _M_code(__ec)',
                '    { }',
                '',
                '    friend void __throw_future_error(int);',
            ]
        ) + "\n"
        rewritten = rewrite_source_content(
            Path("libstdc++-v3/include/std/future"),
            original,
        )
        self.assertIn('#ifdef _GLIBCXX_NONSHARED_CXX11_48\n    future_error(error_code __ec);', rewritten)
        self.assertIn('#else\n    future_error(error_code __ec)\n    : logic_error("std::future_error: " + __ec.message()), _M_code(__ec)', rewritten)
        self.assertIn('#endif\n\n    friend void __throw_future_error(int);', rewritten)

    def test_rewrite_source_content_adds_future48_ctor_definition(self):
        rewritten = rewrite_source_content(
            Path("libstdc++-v3/src/nonshared11/future48.cc"),
            '#define _GLIBCXX_NONSHARED_CXX11_48\n'
            '#include "../c++11/future.cc"\n'
            'asm (".hidden _ZNSt13__future_base13_State_baseV211_Make_ready6_S_runEPv");\n',
        )
        self.assertIn('future_error::future_error(error_code __ec)', rewritten)
        self.assertIn(': logic_error("std::future_error: " + __ec.message()), _M_code(__ec)', rewritten)
        self.assertIn('} // namespace std\n', rewritten)
        self.assertEqual(1, rewritten.count('future_error::future_error(error_code __ec)'))

    def test_rewrite_source_content_adds_fs_ops_path_iterator_instantiations(self):
        rewritten = rewrite_source_content(
            Path("libstdc++-v3/src/nonshared17/fs_ops.cc"),
            '#include "../c++17/fs_ops.cc"\n'
            'asm (".hidden _ZN9__gnu_cxx13stdio_filebufIcSt11char_traitsIcEED0Ev");\n'
            'asm (".hidden _ZSt8_DestroyISt15_Deque_iteratorINSt10filesystem7__cxx114pathERS3_PS3_EEvT_S7_");\n'
            'asm (".hidden _ZSt13move_backwardISt15_Deque_iteratorINSt10filesystem7__cxx114pathERS3_PS3_ES6_ET0_T_S8_S7_");\n'
            'asm (".hidden _ZSt4moveISt15_Deque_iteratorINSt10filesystem7__cxx114pathERS3_PS3_ES6_ET0_T_S8_S7_");\n',
        )
        self.assertIn("using __el7_fs_path_iter = _Deque_iterator<filesystem::path,", rewritten)
        self.assertIn("using __el7_fs_path_deque = deque<filesystem::path>;", rewritten)
        self.assertIn("move<__el7_fs_path_iter, __el7_fs_path_iter>(", rewritten)
        self.assertIn("move_backward<__el7_fs_path_iter, __el7_fs_path_iter>(", rewritten)
        self.assertIn("__el7_fs_path_deque::emplace_back<filesystem::path>(", rewritten)
        self.assertIn("__el7_fs_path_deque::_M_push_back_aux<const filesystem::path&>(", rewritten)
        self.assertIn('//asm (".hidden _ZSt8_DestroyISt15_Deque_iteratorINSt10filesystem7__cxx114pathERS3_PS3_EEvT_S7_");', rewritten)
        self.assertIn('//asm (".hidden _ZSt13move_backwardISt15_Deque_iteratorINSt10filesystem7__cxx114pathERS3_PS3_ES6_ET0_T_S8_S7_");', rewritten)
        self.assertIn('//asm (".hidden _ZSt4moveISt15_Deque_iteratorINSt10filesystem7__cxx114pathERS3_PS3_ES6_ET0_T_S8_S7_");', rewritten)
        self.assertEqual(1, rewritten.count("using __el7_fs_path_iter = _Deque_iterator<filesystem::path,"))

    def test_rewrite_source_content_adds_future48_guards_to_cxx11_future(self):
        original = "\n".join(
            [
                '#if __has_cpp_attribute(clang::require_constant_initialization)',
                '#  define __constinit [[clang::require_constant_initialization]]',
                '#endif',
                '',
                'namespace',
                '{',
                '  struct future_error_category final : public std::error_category',
                '  {',
                '  };',
                '',
                '  __constinit constant_init future_category_instance{};',
                '}',
                '',
                'namespace std _GLIBCXX_VISIBILITY(default)',
                '{',
                '_GLIBCXX_BEGIN_NAMESPACE_VERSION',
                '',
                '  void',
                '  __throw_future_error(int __i __attribute__((unused)))',
                '  { _GLIBCXX_THROW_OR_ABORT(future_error(make_error_code(future_errc(__i)))); }',
                '',
                '  const error_category& future_category() noexcept',
                '  { return future_category_instance.cat; }',
                '',
                '  future_error::~future_error() noexcept { }',
                '',
                '  const char*',
                '  future_error::what() const noexcept { return logic_error::what(); }',
                '',
                '#ifdef _GLIBCXX_HAS_GTHREADS',
                '  __future_base::_Result_base::_Result_base() = default;',
                '',
                '  __future_base::_Result_base::~_Result_base() = default;',
                '',
                '  void',
                '  __future_base::_State_baseV2::_Make_ready::_S_run(void* p)',
                '  {',
                '  }',
            ]
        ) + "\n"
        rewritten = rewrite_source_content(
            Path("libstdc++-v3/src/c++11/future.cc"),
            original,
        )
        self.assertIn('#ifndef _GLIBCXX_NONSHARED_CXX11_48\nnamespace', rewritten)
        self.assertIn('#endif\n\nnamespace std _GLIBCXX_VISIBILITY(default)', rewritten)
        self.assertIn('#ifndef _GLIBCXX_NONSHARED_CXX11_48\n  const error_category& future_category()', rewritten)
        self.assertIn('#ifndef _GLIBCXX_NONSHARED_CXX11_48\n  __future_base::_Result_base::_Result_base() = default;', rewritten)

    def test_rewrite_source_content_adds_future48_guards_to_random(self):
        original = "\n".join(
            [
                '  // Called by old ABI version of random_device::_M_init(const std::string&).',
                '  void',
                '  random_device::_M_init(const char* s, size_t len)',
                '  {',
                '    const std::string token(s, len);',
                '#ifdef USE_MT19937',
                '    _M_init_pretr1(token);',
                '#else',
                '    _M_init(token);',
                '#endif',
                '  }',
                '',
                '  // Only called by code compiled against old releases of libstdc++.',
                '  // Forward the call to _M_getval() and let it decide what to do.',
                '  random_device::result_type',
                '  random_device::_M_getval_pretr1()',
                '  { return _M_getval(); }',
                '',
                '  void',
                '  random_device::_M_fini()',
                '  {',
                '#ifdef _GLIBCXX_USE_DEV_RANDOM',
                '    _M_file = nullptr;',
                '#endif',
                '  }',
                '',
                '  random_device::result_type',
                '  random_device::_M_getval()',
                '  {',
                '#ifdef USE_MT19937',
                '    return _M_mt();',
                '#else',
                '    return ret;',
                '#endif // USE_MT19937',
                '  }',
                '',
                '  // Only called by code compiled against old releases of libstdc++.',
            ]
        ) + "\n"
        rewritten = rewrite_source_content(
            Path("libstdc++-v3/src/c++11/random.cc"),
            original,
        )
        self.assertIn('#ifndef _GLIBCXX_NONSHARED_CXX11_48\n  void\n  random_device::_M_init', rewritten)
        self.assertIn('#ifndef _GLIBCXX_NONSHARED_CXX11_48\n  random_device::result_type\n  random_device::_M_getval_pretr1()', rewritten)
        self.assertIn('#ifndef _GLIBCXX_NONSHARED_CXX11_48\n  void\n  random_device::_M_fini()', rewritten)
        self.assertIn('#ifndef _GLIBCXX_NONSHARED_CXX11_48\n  random_device::result_type\n  random_device::_M_getval()', rewritten)

    def test_rewrite_source_content_adds_future48_guards_to_thread_and_shared_ptr(self):
        shared_ptr = rewrite_source_content(
            Path("libstdc++-v3/src/c++11/shared_ptr.cc"),
            '#ifndef _GLIBCXX_NONSHARED_CXX11_80\n  bad_weak_ptr::~bad_weak_ptr() noexcept = default;\n#endif\n#endif\n\n  bool\n',
        )
        self.assertIn('#ifndef _GLIBCXX_NONSHARED_CXX11_48\n  bad_weak_ptr::~bad_weak_ptr() noexcept = default;', shared_ptr)
        self.assertIn('#endif\n#endif\n#endif\n\n  bool\n', shared_ptr)

        thread = rewrite_source_content(
            Path("libstdc++-v3/src/c++11/thread.cc"),
            "\n".join(
                [
                    '  unsigned int',
                    '  thread::hardware_concurrency() noexcept',
                    '  {',
                    '    int __n = _GLIBCXX_NPROCS;',
                    '    if (__n < 0)',
                    '      __n = 0;',
                    '    return __n;',
                    '  }',
                    '',
                    'namespace this_thread',
                    '{',
                    '  void',
                    '  __sleep_for(chrono::seconds __s, chrono::nanoseconds __ns)',
                    '  {',
                    '#endif',
                    '  }',
                    '}',
                    '_GLIBCXX_END_NAMESPACE_VERSION',
                    '} // namespace std',
                    '#endif // ! NO_SLEEP',
                ]
            ) + "\n",
        )
        self.assertIn('#ifndef _GLIBCXX_NONSHARED_CXX11_48\n  unsigned int\n  thread::hardware_concurrency() noexcept', thread)
        self.assertIn('namespace this_thread\n{\n#ifndef _GLIBCXX_NONSHARED_CXX11_48\n  void\n  __sleep_for', thread)
        self.assertIn('#endif\n  }\n#endif\n}\n_GLIBCXX_END_NAMESPACE_VERSION', thread)

    def test_rewrite_source_content_drops_condition_variable_wait_from_nonshared(self):
        rewritten = rewrite_source_content(
            Path("libstdc++-v3/src/c++11/condition_variable.cc"),
            '\n'.join(
                [
                    '  void',
                    '  condition_variable::wait(unique_lock<mutex>& __lock)',
                    '  {',
                    '    _M_cond.wait(*__lock.mutex());',
                    '  }',
                    '',
                    '#ifndef _GLIBCXX_NONSHARED_CXX11',
                    '  void',
                    '  condition_variable::notify_one() noexcept',
                ]
            ) + '\n',
        )
        self.assertNotIn('condition_variable::wait(unique_lock<mutex>& __lock)', rewritten)
        self.assertIn('#ifndef _GLIBCXX_NONSHARED_CXX11\n  void\n  condition_variable::notify_one() noexcept', rewritten)

    def test_rewrite_source_content_comments_el8_hidden_symbols_for_el7_fs_ops(self):
        rewritten = rewrite_source_content(
            Path("libstdc++-v3/src/nonshared17/cow-fs_ops.cc"),
            '#include "../c++17/cow-fs_ops.cc"\nasm (".hidden _ZNSs4swapERSs");\n',
        )
        self.assertIn('//asm (".hidden _ZNSs4swapERSs");', rewritten)
        self.assertNotIn('\nasm (".hidden _ZNSs4swapERSs");\n', "\n" + rewritten)

    def test_rewrite_source_content_comments_el8_hidden_symbols_for_el7_fs_dir(self):
        rewritten = rewrite_source_content(
            Path("libstdc++-v3/src/nonshared17/cow-fs_dir.cc"),
            '#include "../c++17/cow-fs_dir.cc"\nasm (".hidden _ZNKSt10filesystem4_Dir7currentEv");\n',
        )
        self.assertIn('//asm (".hidden _ZNKSt10filesystem4_Dir7currentEv");', rewritten)
        self.assertNotIn('\nasm (".hidden _ZNKSt10filesystem4_Dir7currentEv");\n', "\n" + rewritten)

    def test_rewrite_source_content_comments_el8_hidden_symbols_for_el7_memory_resource(self):
        rewritten = rewrite_source_content(
            Path("libstdc++-v3/src/nonshared17/memory_resource.cc"),
            '#include "../c++17/memory_resource.cc"\nasm (".hidden _ZNSt22__shared_mutex_pthread6unlockEv");\n',
        )
        self.assertIn('//asm (".hidden _ZNSt22__shared_mutex_pthread6unlockEv");', rewritten)
        self.assertNotIn(
            '\nasm (".hidden _ZNSt22__shared_mutex_pthread6unlockEv");\n',
            "\n" + rewritten,
        )

    def test_rewrite_source_content_comments_el8_hidden_symbols_for_el7_fs_path(self):
        original = "\n".join(
            [
                '#include "../c++17/cow-fs_path.cc"',
                'asm (".hidden _ZNKSt10filesystem4path5_List5_Impl4copyEv");',
                'asm (".hidden _ZNSs6insertEmPKcm");',
                'asm (".hidden _ZNSs6resizeEmc");',
                'asm (".hidden _ZNSs7reserveEm");',
                'asm (".hidden _ZNSs9_M_mutateEmmm");',
                'asm (".hidden _ZNSsC1ERKSsmm");',
                'asm (".hidden _ZNSsC2ERKSsmm");',
                'asm (".hidden _ZNSs12_M_leak_hardEv");',
                'asm (".hidden _ZNSbIwSt11char_traitsIwESaIwEE6resizeEmw");',
                'asm (".hidden _ZNSbIwSt11char_traitsIwESaIwEE7reserveEm");',
                'asm (".hidden _ZNSbIwSt11char_traitsIwESaIwEE9_M_mutateEmmm");',
                'asm (".hidden _ZNSbIwSt11char_traitsIwESaIwEE12_M_leak_hardEv");',
                'asm (".hidden _ZNSt10filesystem4path5_List5beginEv");',
                'asm (".hidden _ZNSt10filesystem4path7_Parser4nextEv");',
                'asm (".hidden _ZNSt10filesystem4pathD1Ev");',
                'asm (".hidden _ZNSt10filesystem4pathD2Ev");',
                'asm (".hidden _ZSt16__do_str_codecvtISbIwSt11char_traitsIwESaIwEEcSt7codecvtIwc11__mbstate_tES5_MS6_KFNSt12codecvt_base6resultERS5_PKcSB_RSB_PwSD_RSD_EEbPKT0_SJ_RT_RKT1_RT2_RmT3_");',
                "",
            ]
        )
        rewritten = rewrite_source_content(
            Path("libstdc++-v3/src/nonshared17/cow-fs_path.cc"),
            original,
        )
        self.assertIn('//asm (".hidden _ZNKSt10filesystem4path5_List5_Impl4copyEv");', rewritten)
        self.assertIn('//asm (".hidden _ZNSs12_M_leak_hardEv");', rewritten)
        self.assertIn(
            '//asm (".hidden _ZNSbIwSt11char_traitsIwESaIwEE12_M_leak_hardEv");',
            rewritten,
        )
        self.assertIn('//asm (".hidden _ZNSt10filesystem4path5_List5beginEv");', rewritten)
        self.assertIn('//asm (".hidden _ZNSt10filesystem4path7_Parser4nextEv");', rewritten)
        self.assertIn('//asm (".hidden _ZNSt10filesystem4pathD1Ev");', rewritten)
        self.assertIn('//asm (".hidden _ZNSt10filesystem4pathD2Ev");', rewritten)
        self.assertIn(
            '//asm (".hidden _ZSt16__do_str_codecvtISbIwSt11char_traitsIwESaIwEEcSt7codecvtIwc11__mbstate_tES5_MS6_KFNSt12codecvt_base6resultERS5_PKcSB_RSB_PwSD_RSD_EEbPKT0_SJ_RT_RKT1_RT2_RmT3_");',
            rewritten,
        )

    def test_rewrite_source_content_comments_el8_hidden_symbols_for_el7_fs_path_cxx11_ucvt(self):
        original = "\n".join(
            [
                '#include "../c++17/fs_path.cc"',
                'asm (".hidden _ZTIZNSt10filesystem7__cxx114path10_S_convertIwEEDaPKT_S5_E5_UCvt");',
                'asm (".hidden _ZTSZNSt10filesystem7__cxx114path10_S_convertIwEEDaPKT_S5_E5_UCvt");',
                'asm (".hidden _ZTVZNSt10filesystem7__cxx114path10_S_convertIwEEDaPKT_S5_E5_UCvt");',
                'asm (".hidden _ZZNSt10filesystem7__cxx114path10_S_convertIwEEDaPKT_S5_EN5_UCvtD0Ev");',
                'asm (".hidden _ZZNSt10filesystem7__cxx114path10_S_convertIwEEDaPKT_S5_EN5_UCvtD1Ev");',
                'asm (".hidden _ZZNSt10filesystem7__cxx114path10_S_convertIwEEDaPKT_S5_EN5_UCvtD2Ev");',
                "",
            ]
        )
        rewritten = rewrite_source_content(
            Path("libstdc++-v3/src/nonshared17/fs_path.cc"),
            original,
        )
        self.assertIn('//asm (".hidden _ZTIZNSt10filesystem7__cxx114path10_S_convertIwEEDaPKT_S5_E5_UCvt");', rewritten)
        self.assertIn('//asm (".hidden _ZTSZNSt10filesystem7__cxx114path10_S_convertIwEEDaPKT_S5_E5_UCvt");', rewritten)
        self.assertIn('//asm (".hidden _ZTVZNSt10filesystem7__cxx114path10_S_convertIwEEDaPKT_S5_E5_UCvt");', rewritten)
        self.assertIn('//asm (".hidden _ZZNSt10filesystem7__cxx114path10_S_convertIwEEDaPKT_S5_EN5_UCvtD2Ev");', rewritten)

    def test_rewrite_source_content_comments_el8_hidden_symbols_for_el7_fs_dir_cxx11_path_ctor(self):
        original = "\n".join(
            [
                '#include "../c++17/fs_dir.cc"',
                'asm (".hidden _ZNSt10filesystem7__cxx114pathC1INSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEES1_EERKT_NS1_6formatE");',
                'asm (".hidden _ZNSt10filesystem7__cxx114pathC2INSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEES1_EERKT_NS1_6formatE");',
                'asm (".hidden _ZNKSt10filesystem7__cxx114_Dir7currentEv");',
                "",
            ]
        )
        rewritten = rewrite_source_content(
            Path("libstdc++-v3/src/nonshared17/fs_dir.cc"),
            original,
        )
        self.assertIn('//asm (".hidden _ZNSt10filesystem7__cxx114pathC1INSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEES1_EERKT_NS1_6formatE");', rewritten)
        self.assertIn('//asm (".hidden _ZNSt10filesystem7__cxx114pathC2INSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEES1_EERKT_NS1_6formatE");', rewritten)
        self.assertIn('//asm (".hidden _ZNKSt10filesystem7__cxx114_Dir7currentEv");', rewritten)

    def test_apply_content_rewrites_updates_existing_fs_overlay_files(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            fs_ops = root / "libstdc++-v3/src/nonshared17/cow-fs_ops.cc"
            fs_path = root / "libstdc++-v3/src/nonshared17/cow-fs_path.cc"
            fs_ops.parent.mkdir(parents=True, exist_ok=True)
            fs_ops.write_text(
                '#include "../c++17/cow-fs_ops.cc"\nasm (".hidden _ZNSs4swapERSs");\n',
                encoding="utf-8",
            )
            fs_path.write_text(
                "\n".join(
                    [
                        '#include "../c++17/cow-fs_path.cc"',
                        'asm (".hidden _ZNKSt10filesystem4path5_List5_Impl4copyEv");',
                        'asm (".hidden _ZNSs6insertEmPKcm");',
                        'asm (".hidden _ZNSs6resizeEmc");',
                        'asm (".hidden _ZNSs7reserveEm");',
                        'asm (".hidden _ZNSs9_M_mutateEmmm");',
                        'asm (".hidden _ZNSsC1ERKSsmm");',
                        'asm (".hidden _ZNSsC2ERKSsmm");',
                        'asm (".hidden _ZNSs12_M_leak_hardEv");',
                        'asm (".hidden _ZNSbIwSt11char_traitsIwESaIwEE6resizeEmw");',
                        'asm (".hidden _ZNSbIwSt11char_traitsIwESaIwEE7reserveEm");',
                        'asm (".hidden _ZNSbIwSt11char_traitsIwESaIwEE9_M_mutateEmmm");',
                        'asm (".hidden _ZNSbIwSt11char_traitsIwESaIwEE12_M_leak_hardEv");',
                        'asm (".hidden _ZNSt10filesystem4path5_List5beginEv");',
                        'asm (".hidden _ZNSt10filesystem4path7_Parser4nextEv");',
                        'asm (".hidden _ZNSt10filesystem4pathD1Ev");',
                        'asm (".hidden _ZNSt10filesystem4pathD2Ev");',
                        'asm (".hidden _ZSt16__do_str_codecvtISbIwSt11char_traitsIwESaIwEEcSt7codecvtIwc11__mbstate_tES5_MS6_KFNSt12codecvt_base6resultERS5_PKcSB_RSB_PwSD_RSD_EEbPKT0_SJ_RT_RKT1_RT2_RmT3_");',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            apply_content_rewrites(root)
            self.assertIn('//asm (".hidden _ZNSs4swapERSs");', fs_ops.read_text(encoding="utf-8"))
            self.assertIn(
                '//asm (".hidden _ZNKSt10filesystem4path5_List5_Impl4copyEv");',
                fs_path.read_text(encoding="utf-8"),
            )
            self.assertIn('//asm (".hidden _ZNSt10filesystem4pathD2Ev");', fs_path.read_text(encoding="utf-8"))

    def test_sync_overlay_tree_skips_build_system_files_by_default(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            overlay = root / "overlay"
            sync = root / "sync"
            tracked = [
                Path("libstdc++-v3/src/Makefile.am"),
                Path("libstdc++-v3/src/nonshared11/future48.cc"),
            ]
            (overlay / tracked[0]).parent.mkdir(parents=True, exist_ok=True)
            (overlay / tracked[0]).write_text("makefile\n", encoding="utf-8")
            (overlay / tracked[1]).parent.mkdir(parents=True, exist_ok=True)
            (overlay / tracked[1]).write_text("future\n", encoding="utf-8")
            written = sync_overlay_tree(sync, overlay, tracked)
            self.assertEqual([tracked[1]], written)
            self.assertFalse((sync / tracked[0]).exists())
            self.assertEqual("future\n", (sync / tracked[1]).read_text(encoding="utf-8"))

    def test_sync_overlay_tree_can_include_build_system_files(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            overlay = root / "overlay"
            sync = root / "sync"
            tracked = [Path("libstdc++-v3/src/Makefile.in")]
            (overlay / tracked[0]).parent.mkdir(parents=True, exist_ok=True)
            (overlay / tracked[0]).write_text("generated\n", encoding="utf-8")
            written = sync_overlay_tree(sync, overlay, tracked, include_build_system=True)
            self.assertEqual(tracked, written)
            self.assertEqual("generated\n", (sync / tracked[0]).read_text(encoding="utf-8"))

    def test_sync_overlay_tree_skips_unchanged_files(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            overlay = root / "overlay"
            sync = root / "sync"
            tracked = [Path("libstdc++-v3/src/nonshared11/future48.cc")]
            (overlay / tracked[0]).parent.mkdir(parents=True, exist_ok=True)
            (overlay / tracked[0]).write_text("same\n", encoding="utf-8")
            (sync / tracked[0]).parent.mkdir(parents=True, exist_ok=True)
            (sync / tracked[0]).write_text("same\n", encoding="utf-8")
            written = sync_overlay_tree(sync, overlay, tracked)
            self.assertEqual([], written)

    def test_update_subdir_makefile_injects_baseline48(self):
        with tempfile.TemporaryDirectory() as tempdir:
            makefile = Path(tempdir) / "Makefile.am"
            makefile.write_text(
                "\n".join(
                    [
                        "noinst_LTLIBRARIES = libnonshared98convenience80.la \\",
                        "\t\t     libnonshared98convenience110.la",
                        "libnonshared98convenience80_la_SOURCES = $(sources) $(sources80)",
                        "libnonshared98convenience110_la_SOURCES = $(sources) $(sources110)",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            update_subdir_makefile(
                makefile,
                "libnonshared98convenience",
                ["extfloat.S", "char8_t-rtti.S"],
            )
            rendered = makefile.read_text(encoding="utf-8")
        self.assertIn("libnonshared98convenience48.la", rendered)
        self.assertIn(
            "libnonshared98convenience48_la_SOURCES = extfloat.S \\\n\tchar8_t-rtti.S",
            rendered,
        )

    def test_update_nonshared11_makefile_injects_special_compile_rules(self):
        with tempfile.TemporaryDirectory() as tempdir:
            makefile = Path(tempdir) / "nonshared11" / "Makefile.am"
            makefile.parent.mkdir(parents=True, exist_ok=True)
            makefile.write_text(
                "\n".join(
                    [
                        "noinst_LTLIBRARIES = libnonshared11convenience80.la \\",
                        "\t\t     libnonshared11convenience110.la",
                        "libnonshared11convenience80_la_SOURCES = $(sources80)",
                        "libnonshared11convenience110_la_SOURCES = $(sources110)",
                        "# Use special rules for source files that require -fchar8_t.",
                        "codecvt80.lo: codecvt80.cc",
                        "\t$(LTCXXCOMPILE) -fchar8_t -c $<",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            update_subdir_makefile(
                makefile,
                "libnonshared11convenience",
                ["del_opa.cc"],
            )
            rendered = makefile.read_text(encoding="utf-8")
        self.assertIn("del_ops.lo: del_ops.cc", rendered)
        self.assertIn("$(LTCXXCOMPILE) -std=gnu++14 -Wno-sized-deallocation -c $<", rendered)
        self.assertIn("del_opa.lo: del_opa.cc", rendered)
        self.assertIn("$(LTCXXCOMPILE) -std=gnu++1z -c $<", rendered)
        self.assertIn("codecvt.lo: codecvt.cc", rendered)
        self.assertIn("codecvt80.lo: codecvt80.cc", rendered)
        self.assertEqual(2, rendered.count("$(LTCXXCOMPILE) -fchar8_t -c $<"))


if __name__ == "__main__":
    unittest.main()
