import gevent
import gevent.pool
import greenlet
from greenlet import GreenletExit
import time
import logging

class Message(object):
	def __init__(self, msg):
		self.msg = msg

class Worker(object):
	def __init__(self, collection, node, response_queue, size=10, max_idle=300):
		self.logger = logging.getLogger('root')
		self.node=node
		self.collection=collection
		self.task_queue=gevent.queue.JoinableQueue(maxsize=0)
		self.response_queue=response_queue
		self.pool = gevent.pool.Pool(size=size)
		self.listener = gevent.spawn(self.handle_actions)
		self.max_idle=max_idle
		self.idle=gevent.spawn(self.timeout)
		gevent.idle()
		self.logger.info("New Worker for {node} created at {time}, can handle {size} tasks in parallel".format(
			node=self.node,time=time.strftime("%H:%M:%S", time.localtime()),size=size))

	def touch(self):
		self.idle.kill()

	def timeout(self):
		try:
			gevent.sleep(self.max_idle)
			self.shutdown()
		except GreenletExit:
			self.idle=gevent.spawn(self.timeout)
			gevent.idle()

	def add_action(self, action):
		self.task_queue.put(action)
		self.logger.debug("[{anum}] Put Action on Worker queue for {node}".format(anum=action.num, node=self.node))
	def shutdown(self):
		self.task_queue.join()
		self.task_queue.put(Message("shutdown"))
		self.task_queue.join()

	def handle_actions(self):
		while True:
			item=self.task_queue.get()
			if isinstance(item, Message):
				if item.msg=="shutdown":
					break
			else:
				self.touch()
				self.pool.spawn(self.run_action(item))
		#self.collection.remove_worker(self)
		self.logger.info("Worker for %s shutdown" % self.node)
		self.task_queue.task_done()

	def run_action(self, action):
		try:
			with gevent.Timeout(action.timeout):
				self.logger.info("[{anum}] Executing {action}".format(
					anum=action.num, action=action))
				result=action.__execute__()
				self.response_queue.put(result)
		except gevent.Timeout:
			if callable(getattr(action, '__timeout__', None)):
				action.__timeout__(action.timeout)
			action.statusmsg = "[{anum}] Execution timed out after {to} seconds.".format(
				anum=action.num, to=action.timeout)
			action.success=False
			self.response_queue.put(action)
			self.logger.warning("[{anum}] Execution of {action} timed out after {to} seconds.".format(
				anum=action.num, action=action, to=action.timeout))
		finally:
			self.touch()
			self.task_queue.task_done()
			self.collection.task_queue.task_done()
			self.logger.debug("[{anum}] Removed Action from Worker queue for {node}".format(
				anum=action.num, node=self.node))
