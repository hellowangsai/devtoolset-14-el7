#include <pthread.h>

static int shared_value;

static void *worker(void *unused) {
  (void) unused;
  shared_value++;
  return 0;
}

int main(void) {
  pthread_t t1, t2;
  pthread_create(&t1, 0, worker, 0);
  pthread_create(&t2, 0, worker, 0);
  pthread_join(t1, 0);
  pthread_join(t2, 0);
  return shared_value == 2 ? 0 : 1;
}
