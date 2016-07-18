import gevent
import greenlet
from greenlet import GreenletExit
import time

class Worker(object):
	def __init__(self, collection, node, response_queue, size=10, max_idle=300):
		self.shutdown=False
		self.node=node
		self.collection=collection
		self.task_queue=gevent.queue.JoinableQueue(maxsize=0)
		self.response_queue=response_queue
		self.greenlets=[gevent.spawn(self.handle_actions, max_idle) for count in range(size)]
		gevent.spawn(self.monitor)
		print("New Worker for {node} created at {time}, can handle {size} tasks in parallel".format(node="x",time=time.strftime("%H:%M:%S", time.localtime()),size=size))

	def monitor(self):
		gevent.joinall(self.greenlets)
		print("Worker for {node} shutdown at {time}".format(node="x",time=time.strftime("%H:%M:%S", time.localtime())))
		self.collection.remove_worker(self)

	def touch(self):
		self.mtime=time.time()

	def add_action(self, action):
		self.task_queue.put(action)

	def handle_actions(self, max_idle=300):
		def expired():
			return time.time() - self.mtime > max_idle
		def idle():
			return self.task_queue.unfinished_tasks == 0
		while not idle() or not expired() and not self.shutdown:
			try:
				with gevent.Timeout(1):
					action=self.task_queue.get()
			except gevent.Timeout:
				continue
			self.touch()
			try:
				with gevent.Timeout(action.timeout):
					self.response_queue.put(action.__execute__())
					print("action done")
			except gevent.Timeout:
				if callable(getattr(action, '__timeout__', None)):
					action.__timeout__(action.timeout)
				action.statusmsg = "Execution timed out after {to} seconds.".format(
					to=action.timeout)
				action.success=False
				self.response_queue.put(action)
				print("Execution timed out after {to} seconds.".format(
					to=action.timeout))
			finally:
				self.touch()
				self.task_queue.task_done()
