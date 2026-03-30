#include <iostream>

extern "C" int legacy_overlap_provider();

int main() {
  const int rc = legacy_overlap_provider();
  if (rc != 0) {
    return rc;
  }

  std::cout << "OK legacy_overlap_main\n";
  return 0;
}
