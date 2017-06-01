import logging, zeep
import requests.exceptions, gevent, hashlib, sys, os, traceback
from arago.pyconnectit.connectors.common.handlers.soap_handler import SOAPHandler
from arago.pyconnectit.common.lmdb_queue import LMDBTaskQueue, Empty, Full

class SyncNetcoolStatus(SOAPHandler):
	def __init__(self, soap_interfaces_map, status_map_map={}):
		super().__init__(soap_interfaces_map)
		def add_status_map(soap_interface, status_map):
			soap_interface.status_map=status_map
			return soap_interface
		self.soap_interfaces_map={
			env:add_status_map(
				soap_interface,
				status_map_map[env])
			for env, soap_interface
			in soap_interfaces_map.items()}

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
						status_code=self.soap_interfaces_map[
							env].status_map[status]
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
		self.sync(
			env,
			data['mand']['eventId'],
			data['free']['eventNormalizedStatus'])

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
		return "{id}:{status}".format(
			id=self.event_id,
			status=self.status)

class ResponseDecodeError(Exception):
	def __init__(self, message):
		Exception.__init__(self, message)
class ProcessLimitExceeded(Exception):
	def __init__(self):
		Exception.__init__(self, "ProcessLimitExceeded")
class NetcoolProcessingError(Exception):
	def __init__(self):
		Exception.__init__(self, "Netcool returned ProcessingError, check queue for invalid data!")
class QueuingError(Exception):
	def __init__(self, message):
		Exception.__init__(self, message)

class BatchSyncNetcoolStatus(SyncNetcoolStatus):
	def __init__(
			self,
			soap_interfaces_map,
			status_map_map={},
			delta_store_map={},
			queue_map={},
			max_items_map={},
			interval_map={}):
		super().__init__(
			soap_interfaces_map,
			status_map_map=status_map_map)
		self.delta_store_map=delta_store_map
		self.queue_map=queue_map
		self.background_jobs=[
			gevent.spawn(
				self.sync, env,
				interface,
				max_items=max_items_map[env],
				interval=interval_map[env])
			for env, interface
			in soap_interfaces_map.items()]

	def calc_netcool_status(
			self,
			event_id,
			event_status_history,
			status_map):
		last_status = event_status_history.pop()['value']
		if last_status == 'Resolved' and any([
				True for item
				in event_status_history
				if item['value'] == 'Escalated']):
			self.logger.verbose("Escalated followed by Resolved => "
								"Resolved_external in Engine, "
								"Escalated in Netcool")
			return (event_id, status_map['Escalated'])
		else:
			return (event_id, status_map[last_status])

	def call_netcool(self, env, netcool_status_string):
		job = gevent.spawn(
			self.soap_interfaces_map[env].netcool_service.runPolicy,
			"get_from_hiro",
			{
				'desc': "HIRORecieveUpdate",
				'format': "String",
				'label': "HIRO2NETCOOL",
				'name': "HIRO2NETCOOL",
				'value': netcool_status_string},
			True)
		gevent.joinall([job])
		return job.get()

	@staticmethod
	def raise_on_error(response):
		try:
			results = {item['name']:item['value']
					   for item
					   in response}
			if results['NetcoolProcessingError'] == 'true':
				raise NetcoolProcessingError()
			if results['ProcessLimitExceeded'] == 'true':
				raise ProcessLimitExceeded()
		except KeyError as e:
			raise ResponseDecodeError(e)

	def sync(self, env, soap_interface, max_items=100, interval=120):
		self.logger.info("Started Netcool background synchronisation "
						 "for {env}, interval is {sleep} seconds, "
						 "forwarding max. {num} items at once.".format(
							 env=env,
							 sleep=interval,
							 num=max_items))
		gevent.sleep(interval)
		while True:
			try:
				with self.queue_map[env].get(
					block=False, max_items=max_items
				) as tasks:
					event_status_list = [
						self.calc_netcool_status(
							status_update.event_id,
							status_update.status['free']['eventNormalizedStatus'],
							soap_interface.status_map
						) for status_update in tasks
					]
					netcool_status_list = [
						event_id + ',' + status_code
						for event_id, status_code in event_status_list
					]
					netcool_status_string = "|".join(netcool_status_list)
					response = self.call_netcool(
						env, netcool_status_string)
					self.raise_on_error(response)
					self.logger.verbose(
						"Forwarding updates to Netcool {env} "
						"succeeded, forwarded {x} items:".format(
							env=env, x=len(tasks)))
			except Empty:
				self.logger.verbose("No tasks in queue for {env}".format(
					env=env))
			except (
					requests.exceptions.ConnectionError,
					requests.exceptions.InvalidURL,
					ResponseDecodeError,
					zeep.exceptions.TransportError
			) as e:
				self.logger.error("SOAP call failed: " + str(e))
			except KeyError:
				self.logger.warning(
					"No SOAPHandler defined for environment: "
					"{env}".format(env=env))
			except Exception as e:
				self.logger.error(
					"SOAP call failed with unknown error:\n"
					+ traceback.format_exc())
			finally:
				self.logger.trace(
					"Current queue store status for {env}:\n{stats}".format(
						env=env,
						stats=self.queue_map[env].stats()))
				gevent.sleep(interval)

	def __call__(self, data, env):
		try:
			event_id = data['mand']['eventId']
			event = self.delta_store_map[env].get_merged(
				event_id)
			status_update = StatusUpdate(event_id, event)
			self.queue_map[env].put(status_update)
		except Full:
			raise QueuingError("Queue full")
		except KeyError:
			self.logger.warn("No queue defined for {env}".format(
				env=env))

	def __str__(self):
		return "BatchSyncNetcoolStatus"
