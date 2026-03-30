#include <future>
#include <iostream>

int main() {
  std::promise<int> promise;
  auto future = promise.get_future();
  (void)future;

  try {
    promise.get_future();
  } catch (const std::future_error& ex) {
    if (ex.code() != std::make_error_code(std::future_errc::future_already_retrieved)) {
      return 2;
    }
    std::cout << "OK future_error\n";
    return 0;
  }

  return 1;
}
