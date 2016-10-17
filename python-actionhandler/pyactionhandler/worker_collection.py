import time
import gevent
from greenlet import GreenletExit
from pyactionhandler.worker import Worker
import sys
import logging
import traceback

class WorkerCollection(object):
	def __init__(self, capabilities, parallel_tasks=10, parallel_tasks_per_worker=10, worker_max_idle=300):
		self.logger = logging.getLogger('root')
		self.capabilities=capabilities
		self.parallel_tasks=parallel_tasks
		self.parallel_tasks_per_worker=parallel_tasks_per_worker
		self.worker_max_idle=worker_max_idle
		self.workers = {}
		self.task_queue=gevent.queue.JoinableQueue(maxsize=0)

	def register_response_queue(self, response_queue):
		self.response_queue=response_queue
		self.logger.info("Registered worker collection for {caps}".format(caps=", ".join(self.capabilities.keys())))

	def get_worker(self, NodeID):
		if NodeID not in self.workers:
			self.workers[NodeID] = Worker(
				self, NodeID, self.response_queue,
				self.parallel_tasks_per_worker,
				self.worker_max_idle)
		return self.workers[NodeID]

	def remove_worker(self, worker):
		self.workers = {n: w for n, w in self.workers.items() if w is not worker}

	def shutdown_workers(self):
		for n,w in self.workers.items(): w.shutdown=True

	def handle_requests_per_worker(self):
		self.logger.info("Started forwarding requests")
		while True:
			anum, capability, timeout, params, zmq_info = self.task_queue.get()
			try:
				worker = self.get_worker(params['NodeID'])
				capability = self.capabilities[capability]
				worker.add_action(capability.action_class(
					anum, params['NodeID'], zmq_info, timeout,
					params, **capability.params))
				del worker, capability
			except KeyError:
				self.logger.error("Unknown capability {cap}".format(cap=capability))
			except Exception as e:
				self.logger.debug(e)
				self.logger.critical("ACTIONHANDLER CRASHED DURING ACTION INIT!!!\n{tb}".format(
					tb=traceback.format_exc()))
