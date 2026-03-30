#include <ctime>
#include <iomanip>
#include <iostream>
#include <locale>
#include <sstream>

int main() {
  const std::locale loc = std::locale::classic();
  const auto& ctype = std::use_facet<std::ctype<char>>(loc);

  if (ctype.widen('x') != 'x') {
    return 1;
  }
  if (ctype.narrow('y', '?') != 'y') {
    return 2;
  }

  std::tm narrow_tm = {};
  std::istringstream narrow_stream("2026-03-28 12:34:56");
  narrow_stream.imbue(loc);
  narrow_stream >> std::get_time(&narrow_tm, "%Y-%m-%d %H:%M:%S");
  if (narrow_stream.fail()) {
    return 3;
  }

  std::tm wide_tm = {};
  std::wistringstream wide_stream(L"2026-03-28 12:34:56");
  wide_stream.imbue(loc);
  wide_stream >> std::get_time(&wide_tm, L"%Y-%m-%d %H:%M:%S");
  if (wide_stream.fail()) {
    return 4;
  }

  std::cout << "OK locale_time_get\n";
  return 0;
}
