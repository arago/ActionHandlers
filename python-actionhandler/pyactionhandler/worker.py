import gevent
import greenlet
from greenlet import GreenletExit
import time
import logging

class Worker(object):
	def __init__(self, collection, node, response_queue, size=10, max_idle=300):
		self.logger = logging.getLogger('worker')
		self.shutdown=False
		self.node=node
		self.collection=collection
		self.task_queue=gevent.queue.JoinableQueue(maxsize=0)
		self.response_queue=response_queue
		self.greenlets=[gevent.spawn(self.handle_actions, max_idle) for count in range(size)]
		gevent.spawn(self.monitor)
		self.logger.info("New Worker for {node} created at {time}, can handle {size} tasks in parallel".format(node=self.node,time=time.strftime("%H:%M:%S", time.localtime()),size=size))

	def monitor(self):
		gevent.joinall(self.greenlets)
		self.logger.info("Worker for %s shutdown" % self.node)
		self.collection.remove_worker(self)

	def touch(self):
		self.mtime=time.time()

	def add_action(self, action):
		self.task_queue.put(action)
		self.logger.debug(
			"Put Action on Worker queue for {node}, {num} unfinished tasks".format(node=self.node,num=self.task_queue.unfinished_tasks))
	def handle_actions(self, max_idle=300):
		def expired():
			return time.time() - self.mtime > max_idle
		def idle():
			return self.task_queue.unfinished_tasks == 0
		while not idle() or not expired() and not self.shutdown:
			try:
				with gevent.Timeout(0.1):
					action=self.task_queue.get()
			except gevent.Timeout:
				continue
			self.touch()
			try:
				with gevent.Timeout(action.timeout):
					self.logger.debug("Executing Action %s" % str(action))
					self.response_queue.put(action.__execute__())
			except gevent.Timeout:
				if callable(getattr(action, '__timeout__', None)):
					action.__timeout__(action.timeout)
				action.statusmsg = "Execution timed out after {to} seconds.".format(to=action.timeout)
				action.success=False
				self.response_queue.put(action)
				self.logger.warning("Execution of {action} timed out after {to} seconds.".format(action=action, to=action.timeout))
			finally:
				self.touch()
				self.task_queue.task_done()
				self.logger.debug(
					"Removed Action from Worker queue for {node}, {num} unfinished tasks".format(node=self.node,num=self.task_queue.unfinished_tasks))
