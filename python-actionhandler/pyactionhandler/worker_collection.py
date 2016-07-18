import time
import gevent
from pyactionhandler.worker import Worker
import sys

class WorkerCollection(object):
	def __init__(self, size_per_worker=10, max_idle=300):
		self.size_per_worker=size_per_worker
		self.max_idle=max_idle
		self.workers = {}

	def get_worker(self, NodeID, response_queue):
		if NodeID not in self.workers:
			self.workers[NodeID] = Worker(
				self,
				NodeID,
				response_queue,
				self.size_per_worker,
				self.max_idle)
		return self.workers[NodeID]

	def remove_worker(self, worker):
		self.workers = {n: w for n, w in self.workers.items() if w is not worker}
