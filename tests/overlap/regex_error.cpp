#include <iostream>
#include <regex>
#include <string>

int main() {
  try {
    std::regex invalid("(", std::regex::extended);
    (void)invalid;
  } catch (const std::regex_error& ex) {
    if (std::string(ex.what()).empty()) {
      return 2;
    }
    std::cout << "OK regex_error\n";
    return 0;
  }

  return 1;
}
