#include <limits.h>

int main(void) {
    volatile int x = INT_MAX;
    return x + 1;
}
