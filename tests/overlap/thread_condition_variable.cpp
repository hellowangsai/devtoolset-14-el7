#include <chrono>
#include <condition_variable>
#include <iostream>
#include <mutex>
#include <thread>

int main() {
  std::condition_variable cv;
  std::mutex mutex;
  bool ready = false;
  bool exited = false;
  bool detached_done = false;

  std::thread joined([&] {
    std::unique_lock<std::mutex> lock(mutex);
    ready = true;
    cv.notify_one();
    exited = true;
    std::notify_all_at_thread_exit(cv, std::move(lock));
  });

  {
    std::unique_lock<std::mutex> lock(mutex);
    cv.wait(lock, [&] { return ready; });
    cv.wait(lock, [&] { return exited; });
  }

  joined.join();

  std::thread detached([&] {
    std::unique_lock<std::mutex> lock(mutex);
    detached_done = true;
    cv.notify_one();
  });
  detached.detach();

  {
    std::unique_lock<std::mutex> lock(mutex);
    if (!cv.wait_for(lock, std::chrono::seconds(5), [&] { return detached_done; })) {
      return 2;
    }
  }

  std::cout << "OK thread_condition_variable\n";
  return 0;
}
