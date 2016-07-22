import time
import gevent
from greenlet import GreenletExit
from pyactionhandler.worker import Worker
import sys
import logging

class WorkerCollection(object):
	def __init__(self, action_classes, parallel_tasks=10, parallel_tasks_per_worker=10, worker_max_idle=300):
		self.logger = logging.getLogger('worker_collection')
		self.action_classes=action_classes
		self.parallel_tasks=parallel_tasks
		self.parallel_tasks_per_worker=parallel_tasks_per_worker
		self.worker_max_idle=worker_max_idle
		self.workers = {}
		self.task_queue=gevent.queue.JoinableQueue(maxsize=0)

	def register_response_queue(self, response_queue):
		self.response_queue=response_queue
		self.logger.info("Registered worker collection for {caps}".format(caps=", ".join(self.action_classes.keys())))

	def get_worker(self, NodeID, response_queue):
		if NodeID not in self.workers:
			self.workers[NodeID] = Worker(
				self,
				NodeID,
				response_queue,
				self.parallel_tasks_per_worker,
				self.worker_max_idle)
		return self.workers[NodeID]

	def remove_worker(self, worker):
		self.workers = {n: w for n, w in self.workers.items() if w is not worker}

	def shutdown_workers(self):
		for n,w in self.workers.items():
			w.shutdown=True

	def handle_requests_per_worker(self):
		self.logger.info("Started forwarding requests")
		while True:
			anum, capability, timeout, params, zmq_info = self.task_queue.get()
			try:
				self.get_worker(
					params['NodeID'], self.response_queue).add_action(
						self.action_classes[capability][0](
							anum,
							params['NodeID'],
							zmq_info,
							timeout,
							params,
							**self.action_classes[capability][1]))
			except KeyError:
				self.logger.error("Unknown capability")
