#include <iostream>
#include <sstream>
#include <string>

int main() {
  std::istringstream stream("overlap-smoke");
  stream.exceptions(std::ios::failbit | std::ios::badbit);

  try {
    stream.clear(std::ios::failbit);
  } catch (const std::ios_base::failure& ex) {
    if (std::string(ex.what()).empty()) {
      return 2;
    }
    std::cout << "OK ios_failure\n";
    return 0;
  }

  return 1;
}
