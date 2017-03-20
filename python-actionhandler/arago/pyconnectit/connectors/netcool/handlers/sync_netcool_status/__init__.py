from random import choice
import requests.exceptions, gevent, hashlib, sys
from arago.pyconnectit.connectors.common.handlers.soap_handler import SOAPHandler
from arago.pyconnectit.common.lmdb_queue import LMDBTaskQueue, Empty

class SyncNetcoolStatus(SOAPHandler):
	def __init__(self, soap_interfaces_map):
		super().__init__(soap_interfaces_map)

	@classmethod
	def from_config(cls, adapter_config, environments_config, prefix='netcool_'):
		return super().from_config(adapter_config, environments_config, prefix=prefix)

	def sync(self, env, event_id, status):
		try:
			self.soap_interfaces_map[env].netcool_service.runPolicy(
				"get_from_hiro", {
					'desc': "HIRORecieveUpdate",
					'format': "String",
					'label': "HIRO2NETCOOL",
					'name': "HIRO2NETCOOL",
					'value': "{event_id},{status_code}|".format(
						event_id=event_id,
						status_code=self.soap_interfaces_map[env].status_map[status]
					)
				}, True)
		except requests.exceptions.ConnectionError as e:
			self.logger.error("SOAP call failed: " + str(e))
		except requests.exceptions.InvalidURL as e:
			self.logger.error("SOAP call failed: " + str(e))
		except KeyError:
			self.logger.warning(
				"No SOAPHandler defined for environment: {env}".format(
					env=env))

	def __call__(self, data, env):
		self.sync(env, data['mand']['eventId'], data['free']['eventNormalizedStatus'])

	def __str__(self):
		return "SyncNetcoolStatus"

class StatusUpdate(object):
	def __init__(self, event_id, status):
		self.event_id=event_id
		self.status=status
	def __hash__(self):
		return int.from_bytes(
			hashlib.sha1(self.event_id.encode('utf-8')).digest(),
			byteorder=sys.byteorder,
			signed=True)
	def __eq__(self, other):
		return self.event_id == other.event_id and self.status == other.status
	def __str__(self):
		return "{id}:{status}".format(id=self.event_id, status=self.status)

class BatchSyncNetcoolStatus(SyncNetcoolStatus):
	def __init__(self, soap_interfaces_map):
		super().__init__(soap_interfaces_map)
		self.queue = LMDBTaskQueue('/tmp/testq1')
		self.background_job=gevent.spawn(self.sync, "test", max_items=50, sleep_interval=10)

	def sync(self, soap_interface, max_items=100, sleep_interval=60):
		self.logger.info("Started Netcool background synchronisation, interval is {sleep} seconds, forwarding max. {num} items at once.".format(sleep=sleep_interval, num=max_items))
		gevent.sleep(sleep_interval)
		while True:
			try:
				txn, tasks = self.queue.get(block=False, max_items=max_items)
				if choice([True, False]):
					self.logger.debug(
						"Forwarding updates to Netcool succeeded, forwarded {x} items:".format(x=len(tasks)))
					txn.commit()
				else:
					self.logger.error("Netcool not reacheable, aborting!")
					txn.abort()
			except Empty:
				self.logger.debug("No tasks in queue")
			finally:
				self.logger.trace("Current Queue status:\n" + self.queue.stats())
				gevent.sleep(sleep_interval)

	def __call__(self, data, env):
		self.queue.put(
			StatusUpdate(
				data['mand']['eventId'],
				data['free']['eventNormalizedStatus']))

	def __str__(self):
		return "BatchSyncNetcoolStatus"
