import queue

class DroppingQueue(queue.Queue):
    """
    A queue that drops the oldest item when it is full.
    """
    def put(self, item, block=True, timeout=None):
        """
        Put an item into the queue.

        If the queue is full, it drops the oldest item and adds the new one.

        This operation is atomic with respect to other producers: under concurrent
        access, `put_nowait()` will not raise `queue.Full` because this method
        always makes space (by dropping the oldest element) before enqueuing.
        """
        # Note: We intentionally do NOT call super().put(), because Queue.put()
        # may raise queue.Full when called with block=False. Instead, we perform
        # a "drop oldest (if needed) + put" as one critical section under the
        # queue's internal mutex.
        with self.mutex:
            if self.maxsize > 0 and self._qsize() >= self.maxsize:
                # Drop exactly one oldest item to make room.
                self._get()

                # If users rely on join()/task_done(), dropped work should not
                # keep join() waiting forever.
                if self.unfinished_tasks > 0:
                    self.unfinished_tasks -= 1

            self._put(item)
            self.unfinished_tasks += 1
            self.not_empty.notify()

    def put_nowait(self, item):
        """
        Put an item into the queue without blocking.

        If the queue is full, it drops the oldest item and adds the new one.
        """
        self.put(item, block=False)
