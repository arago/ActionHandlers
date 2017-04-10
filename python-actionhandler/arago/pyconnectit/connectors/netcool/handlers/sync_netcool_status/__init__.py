import logging, zeep
import requests.exceptions, gevent, hashlib, sys, os
from arago.pyconnectit.connectors.common.handlers.soap_handler import SOAPHandler
from arago.pyconnectit.common.lmdb_queue import LMDBTaskQueue, Empty

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

	@classmethod
	def from_config(
			cls,
			adapter_config,
			environments_config,
			prefix='netcool_',
			*args,
			**kwargs):
		status_map_map={
			env:{status.replace(
				prefix + 'status_', '', 1).capitalize():code
				 for status, code
				 in environments_config['DEFAULT'].items()
				 if status.startswith('netcool_status_')}
			for env
			in environments_config.sections()}
		return super().from_config(
			adapter_config,
			environments_config,
			prefix=prefix,
			status_map_map=status_map_map,
			*args,
			**kwargs)

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

	@classmethod
	def from_config(
			cls,
			adapter_config,
			environments_config,
			delta_store_map={},
			prefix='netcool_'):
		path = adapter_config['Queue']['data_dir']
		try:
			os.makedirs(path, mode=0o700, exist_ok=True)
		except OSError as e:
			logger=logging.getLogger('root')
			logger.critical("Can't create data directory: " + e)
			sys.exit(5)
		queue_map = {env:LMDBTaskQueue(
			os.path.join(path, env),
			disksize = 1024 * 1024 * adapter_config.getint(
				'Queue', 'max_size_in_mb', fallback=200))
					 for env
					 in environments_config.sections()}
		max_items_map = {
			env:environments_config.getint(
				env, prefix + 'sync_amount',
				fallback=100)
			for env in environments_config.sections()}
		interval_map = {
			env:environments_config.getint(
				env, prefix + 'sync_interval_in_seconds',
				fallback=60)
			for env in environments_config.sections()}
		return super().from_config(
			adapter_config,
			environments_config,
			delta_store_map=delta_store_map,
			queue_map=queue_map,
			max_items_map=max_items_map,
			interval_map=interval_map,
			prefix=prefix)

	def gen_event_status_list(self, env, tasks, status_map):
		return [self.calc_netcool_status(
			status_update.event_id,
			status_update.status['free']['eventNormalizedStatus'],
			status_map)
				for status_update in tasks]

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
	def gen_netcool_status_string(event_status_list):
		string = ''
		for event_id, status_code in event_status_list:
			string += event_id + ',' + status_code + '|'
		return string

	@staticmethod
	def decode_response(response):
		try:
			results = {item['name']:item['value']
					   for item
					   in response}
			if results['NetcoolProcessingError'] == 'true':
				NetcoolProcessingError = True
			else:
				NetcoolProcessingError = False
			if results['ProcessLimitExceeded'] == 'true':
				ProcessLimitExceeded = True
			else:
				ProcessLimitExceeded = False
			return (NetcoolProcessingError, ProcessLimitExceeded)
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
				txn, tasks = self.queue_map[env].get(
					block=False, max_items=max_items)
				netcool_status_string = self.gen_netcool_status_string(
					self.gen_event_status_list(
						env,
						tasks,
						soap_interface.status_map))
				try:
					response = self.call_netcool(
						env, netcool_status_string)
					NetcoolProcessingError, ProcessLimitExceeded = self.decode_response(response)
					if ProcessLimitExceeded:
						self.logger.error(
							"Netcool process limit exceeded, aborting!")
						txn.abort()
						self.queue_map[env]._sem.release()
					elif NetcoolProcessingError:
						self.logger.error(
							"Netcool processing error, aborting!")
						txn.abort()
						self.queue_map[env]._sem.release()
					else:
						self.logger.verbose(
							"Forwarding updates to Netcool {env} "
							"succeeded, forwarded {x} items:".format(
								env=env, x=len(tasks)))
						txn.commit()
						self.queue_map[env]._sem.release()
				except (requests.exceptions.ConnectionError,
						requests.exceptions.InvalidURL,
						ResponseDecodeError,
						zeep.exceptions.TransportError) as e:
					self.logger.error("SOAP call failed: " + str(e))
					txn.abort()
					self.queue_map[env]._sem.release()
				except KeyError:
					self.logger.warning(
						"No SOAPHandler defined for environment: "
						"{env}".format(
							env=env))
					txn.abort()
					self.queue_map[env]._sem.release()
			except Empty:
				self.logger.debug("No tasks in queue for {env}".format(
					env=env))
			finally:
				self.logger.trace(("Current queue store status for "
								   "{env}:\n").format(env=env)
								  + self.queue_map[env].stats())
				gevent.sleep(interval)

	def __call__(self, data, env):
		try:
			self.queue_map[env].put(
				StatusUpdate(
					data['mand']['eventId'],
					self.delta_store_map[env].get_merged(
						data['mand']['eventId'])))
		except KeyError:
			self.logger.warn("No queue defined for {env}".format(
				env=env))

	def __str__(self):
		return "BatchSyncNetcoolStatus"
