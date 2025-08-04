import queue

class DroppingQueue(queue.Queue):
    """
    A queue that drops the oldest item when it is full.
    """
    def put(self, item, block=True, timeout=None):
        """
        Put an item into the queue.

        If the queue is full, it drops the oldest item and adds the new one.
        """
        if self.full():
            try:
                # Remove the oldest item
                self.get_nowait()
            except queue.Empty:
                # This can happen in a race condition, it's fine.
                pass
        
        # Add the new item
        super().put(item, block, timeout)

    def put_nowait(self, item):
        """
        Put an item into the queue without blocking.

        If the queue is full, it drops the oldest item and adds the new one.
        """
        self.put(item, block=False)
