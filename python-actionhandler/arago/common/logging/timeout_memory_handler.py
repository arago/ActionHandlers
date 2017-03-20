import logging, gevent

class TimeoutMemoryHandler(logging.handlers.MemoryHandler):
	def __init__(self, capacity, flushLevel=logging.ERROR,
				 target=None, timeout=10):
		super().__init__(capacity, flushLevel, target)
		self.timeout=timeout
		gevent.spawn(self.flushOnTimeout)

	def flushOnTimeout(self):
		while True:
			gevent.sleep(self.timeout)
			self.flush()
