import logging, zeep
import requests.exceptions, gevent, hashlib, sys, os, traceback
from arago.pyconnectit.connectors.common.handlers.base_handler import BaseHandler
from arago.pyconnectit.common.lmdb_queue import LMDBTaskQueue, Empty, Full
import fastjsonschema, time, ujson as json

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

class NetcoolBatchSyncer(BaseHandler):
	def __init__(self, env, soap_interface, status_map, queue, max_items, interval):
		super().__init__()
		self.env=env
		self.soap_interface=soap_interface
		self.status_map=status_map
		self.queue=queue
		self.loop=gevent.Greenlet(self.sync, max_items, interval)

	def start(self):
		self.loop.start()

	def halt(self):
		self.loop.kill()

	def serve_forever(self):
		self.loop.start()
		self.loop.join()

	def call_netcool(self, netcool_status_string):
		job = gevent.spawn(
			self.soap_interface.netcool_service.runPolicy,
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

	def sync(self, max_items=100, interval=120):
		self.logger.info("Started Netcool background synchronisation "
						 "for {env}, interval is {sleep} seconds, "
						 "forwarding max. {num} items at once.".format(
							 env=self.env,
							 sleep=interval,
							 num=max_items))
		gevent.sleep(interval)
		while True:
			try:
				with self.queue.get(
					block=False, max_items=max_items
				) as tasks:
					event_status_list = []
					for status_update in tasks:
						if status_update:
							try:
								status_string = status_update.status['free']['eventNormalizedStatus'].pop()['value']
								status_code = self.status_map[status_string]
								event_status_list.append((status_update.event_id, status_code))
							except KeyError:
								self.logger.warning("Unknown status: {status}, ignoring".format(
									status=status_string))
					netcool_status_list = [
						event_id + ',' + status_code
						for event_id, status_code in event_status_list
					]
					netcool_status_string = "|".join(netcool_status_list)
					response = self.call_netcool(netcool_status_string)
					self.raise_on_error(response)
					self.logger.info(
						"Forwarding updates to Netcool {env} "
						"succeeded, forwarded {x} items:".format(
							env=self.env, x=len(tasks)))
			except Empty:
				self.logger.verbose("No tasks in queue for {env}".format(
					env=self.env))
			except (
					requests.exceptions.ConnectionError,
					requests.exceptions.InvalidURL,
					ResponseDecodeError,
					zeep.exceptions.TransportError,
					NetcoolProcessingError
			) as e:
				self.logger.error("SOAP call failed: " + str(e))
			except KeyError as e:
				if e.args[0] == self.env:
					self.logger.warning(
						"No SOAPHandler defined for environment: "
						"{env}".format(env=self.env))
				else:
					self.logger.error(
						"Forwarding to Netcool failed with an unknown error:\n"
						+ traceback.format_exc())
			except Exception as e:
				self.logger.error(
					"SOAP call failed with unknown error:\n"
					+ traceback.format_exc())
			finally:
				# self.logger.trace(
				# 	"Current queue store status for {env}:\n{stats}".format(
				# 		env=self.env,
				# 		stats=self.queue.stats()))
				gevent.sleep(interval)

class ForwardStatus(object):
	def __init__(self, delta_store_map={}, queue_map={}):
		self.delta_store_map=delta_store_map
		self.queue_map=queue_map

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
		except Exception:
			self.logger.error("Forwarding status of event {ev} failed with unknown error:\n"
							  + traceback.format_exc())

	def __str__(self):
		return "ForwardStatus"

class EndStateReached(Exception):
	pass

class SetStatus(object):
	def __init__(self, status, delta_store_map={}, queue_map={}, end_state_schemas=[]):
		self.logger = logging.getLogger('root')
		self.status=status
		self.delta_store_map=delta_store_map
		self.queue_map=queue_map
		self.end_states=[fastjsonschema.compile(json.load(schemafile)) for schemafile in end_state_schemas]

	def catch_endstates(self, event_id, event):
		for end_state in self.end_states:
			try:
				end_state(event)
				self.logger.verbose(
					("Event {evt} has reached one of the defined end states, "
					 "not forwarding any updates").format(evt=event_id))
				raise EndStateReached()
			except fastjsonschema.JsonSchemaException:
				self.logger.debug(
					("Event {evt} has not yet reached any one of the defined end states, "
					 "forwarding updates").format(evt=event_id))

	def __call__(self, data, env):
		try:
			event_id = data['mand']['eventId']
			event = self.delta_store_map[env].get_merged(
				event_id)
			#event['free']['eventNormalizedStatus'][-1]['value']=self.status
			try:
				self.catch_endstates(event_id, event)
			except EndStateReached:
				return
			try:
				event['free']['eventNormalizedStatus'].append({'value':self.status, 'timestamp':str(int(time.time() * 1000))})
			except KeyError as e:
				if e.args[0] == 'eventNormalizedStatus':
					event['free']['eventNormalizedStatus'] = [
						{'value':self.status,
						 'timestamp':str(int(time.time() * 1000))}]
				elif e.args[0] == 'free':
					event['free'] = {'eventNormalizedStatus': [
							{'value':self.status,
							 'timestamp':str(int(time.time() * 1000))}]}
				else:
					raise
			status_update = StatusUpdate(event_id, event)
			self.queue_map[env].put(status_update)
		except Full:
			raise QueuingError("Queue full")
		except KeyError:
			self.logger.warn("No queue defined for {env}".format(
				env=env))
		except Exception:
			self.logger.error("Setting status of event {ev} failed with unknown error:\n"
							  + traceback.format_exc())

	def __str__(self):
		return "SetStatus ({status})".format(status=self.status)
