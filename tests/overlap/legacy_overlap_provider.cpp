#include <condition_variable>
#include <ctime>
#include <future>
#include <iomanip>
#include <locale>
#include <mutex>
#include <regex>
#include <sstream>
#include <string>
#include <thread>

extern "C" int legacy_overlap_provider() {
  try {
    std::istringstream stream("legacy-overlap-smoke");
    stream.exceptions(std::ios::failbit | std::ios::badbit);
    stream.clear(std::ios::failbit);
    return 1;
  } catch (const std::ios_base::failure& ex) {
    if (std::string(ex.what()).empty()) {
      return 2;
    }
  }

  try {
    std::regex invalid("(", std::regex::extended);
    (void)invalid;
    return 3;
  } catch (const std::regex_error& ex) {
    if (std::string(ex.what()).empty()) {
      return 4;
    }
  }

  std::promise<int> promise;
  auto future = promise.get_future();
  (void)future;
  try {
    promise.get_future();
    return 5;
  } catch (const std::future_error& ex) {
    if (ex.code() != std::make_error_code(std::future_errc::future_already_retrieved)) {
      return 6;
    }
  }

  const std::locale loc = std::locale::classic();
  std::tm tm_value = {};
  std::wistringstream wide_stream(L"2026-03-28 12:34:56");
  wide_stream.imbue(loc);
  wide_stream >> std::get_time(&tm_value, L"%Y-%m-%d %H:%M:%S");
  if (wide_stream.fail()) {
    return 7;
  }

  std::condition_variable cv;
  std::mutex mutex;
  bool done = false;

  std::thread joined([&] {
    std::unique_lock<std::mutex> lock(mutex);
    done = true;
    std::notify_all_at_thread_exit(cv, std::move(lock));
  });

  {
    std::unique_lock<std::mutex> lock(mutex);
    cv.wait(lock, [&] { return done; });
  }

  joined.join();
  return 0;
}
