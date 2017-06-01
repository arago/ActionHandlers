import logging, zeep
import requests.exceptions, gevent, hashlib, sys, os, traceback, re, datetime
from arago.pyconnectit.connectors.common.handlers.soap_handler import SOAPHandler
from arago.pyconnectit.common.lmdb_queue import LMDBTaskQueue, Empty, Full

class IDTransformator(object):
	def __init__(self):
		self.snow_regex = re.compile(r"")
		self.snow_fmt = "{}:{}"

		self.arago_regex = re.compile(r"^(?P<serial>[0-9]+)(?P<server>.+)$")
		self.arago_fmt = ""

		self.netcool_regex = re.compile(r"")
		self.netcool_fmt = ""

	def arago_in(self, arago_fmt):
		result = self.arago_regex.search(arago_fmt)
		if result:
			return (result.group('server'), result.group('serial'))

	def snow_out(self, data):
		if data:
			return self.snow_fmt.format(*data)

class OpenSnowTicket(SOAPHandler):
	def __init__(
			self,
			soap_interfaces_map,
			delta_store_map={}):
		super().__init__(soap_interfaces_map)
		self.delta_store_map=delta_store_map
		self.id_transform = IDTransformator()

	def sync(self, env, event_id, status):
		event = self.delta_store_map[env].get_merged(event_id)
		self.logger.info(event)
		try:
			try:
				INKA = event['free']['INKA']
			except KeyError:
				raise SnowError("No INKA number in event data!")
			result = self.soap_interfaces_map[env].snow_service.execute(
				UBStable="incident",
				UBSaction="create",
				system=INKA,
				summary=event['mand']['description'],
				details="Severity={sev}, Location={loc}, OwnerGID={gid}, Subclass={subc}, FirstOccurrence={fo}, LastOccurrence={lo}, Tally={t}".format(
					sev=event['opt']['severity'] if 'opt' in event and 'severity' in event['opt'] else "",
					loc="", # Stamford ???
					gid="", # 1468 ???
					subc="", # "UNIX" ???
					fo=event['opt']['firstOccurredAt'] if 'opt' in event and 'firstOccurredAt' in event['opt'] else "", # FIXME: date format
					lo="", # FIXME: Where do I get lastOccurrence from?
					t="" # ???
				),
				netcool_id = self.id_transform.snow_out(self.id_transform.arago_in(event_id)) or "",
				arago_id=event_id, # FIXME: issue_id statt event_id
				notes="\n\n".join("{time}:\n{comment}".format(time=datetime.datetime.fromtimestamp(int(comment['opt']['timestamp'])/1000).strftime('%Y-%m-%d %H:%M:%S'),comment=comment['opt']['content']) for comment in sorted(event['opt']['comment'], key=lambda comment: comment['opt']['timestamp'])) #,
				# error_code="",
				# transaction_time="2016-05-11 09:14:33" # now???
			)
			if result.UBSstatus == 'success' and result.inc_number:
				self.logger.info("Created incident ticket in ServiceNow, incident no is: {no}".format(
					no=result.inc_number))
			else:
				self.logger.error("Creating incident ticket in ServiceNow failed: {err}".format(
					err=result.UBSerror_message if result.UBSerror_message else "Unknown error"))
		except zeep.exceptions.TransportError as e:
			self.logger.error("SOAP call failed: " + str(e))
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
		Exception.__init__(self, "NetcoolProcessingError")
class QueuingError(Exception):
	def __init__(self, message):
		Exception.__init__(self, message)
class SnowError(Exception):
	def __init__(self, message):
		Exception.__init__(self, message)

class BatchOpenSnowTicket(OpenSnowTicket):
	def __init__(
			self,
			soap_interfaces_map,
			delta_store_map={},
			queue_map={}):
		super().__init__(
			soap_interfaces_map,
			delta_store_map=delta_store_map)
		self.queue_map=queue_map
		self.background_jobs=[
			gevent.spawn(self.sync, env, interface)
			for env, interface
			in soap_interfaces_map.items()]
		self.default_pause=0.01
		self.default_step=0.01
		self.default_factor=1.5
		self.default_limit=120

	@staticmethod
	def raise_on_error(response):
		if response.UBSstatus == 'success' and response.inc_number:
			return
		raise SnowError(response.UBSerror_message if response.UBSerror_message else "Unknown error")

	def sync(self, env, soap_interface):
		self.logger.info("Started ServiceNow background synchronisation "
						 "for {env}.".format(env=env))
		pause=self.default_pause
		step = self.default_step
		gevent.sleep(pause)
		while True:
			try:
				with self.queue_map[env].get(
					block=True, max_items=1
				) as tasks:
					for status_update in tasks:
						try:
							INKA = status_update.status['free']['INKA']
						except KeyError:
							self.logger.error(
								"Cannot create incident ticket for event {id}, "
								"no INKA number in event data!".format(
									id=status_update.event_id))
							continue
						try:
							IID = status_update.status['free']['IID']
						except KeyError:
							self.logger.error(
								"Cannot create incident ticket for event {id}, "
								"no Issue ID in event data!".format(
									id=status_update.event_id))
							continue
						response = self.soap_interfaces_map[env].snow_service.execute(
							UBStable="incident",
							UBSaction="create",
							system=INKA,
							summary=status_update.status['mand']['description'],
							details="Severity={sev}, Location={loc}, OwnerGID={gid}, Subclass={subc}, FirstOccurrence={fo}, LastOccurrence={lo}, Tally={t}".format(
								sev=status_update.status['opt']['severity'] if 'opt' in status_update.status and 'severity' in status_update.status['opt'] else "",
								loc="", # Stamford ???
								gid="", # 1468 ???
								subc="", # "UNIX" ???
								fo=status_update.status['opt']['firstOccurredAt'] if 'opt' in status_update.status and 'firstOccurredAt' in status_update.status['opt'] else "", # FIXME: date format
								lo="", # FIXME: Where do I get lastOccurrence from?
								t="" # ???
							),
							netcool_id = self.id_transform.snow_out(self.id_transform.arago_in(status_update.event_id)) or "",
							arago_id=IID,
							notes="\n\n".join("{time}:\n{comment}".format(time=datetime.datetime.fromtimestamp(int(comment['opt']['timestamp'])/1000).strftime('%Y-%m-%d %H:%M:%S'),comment=comment['opt']['content']) for comment in sorted(status_update.status['opt']['comment'], key=lambda comment: comment['opt']['timestamp'])) #,
							# error_code="",
							# transaction_time="2016-05-11 09:14:33" # now???
						)
								# status_update.event_id,
								# status_update.status['free']['eventNormalizedStatus']
						self.raise_on_error(response)
						self.logger.info("Incident ticket {inc} created for issue {iid} (Netcool event {nc})".format(inc=response.inc_number, iid=IID, nc=status_update.event_id))
						if pause != self.default_pause:
							pause = self.default_pause
							step = self.default_step
							self.logger.debug("Backoff delay reset to {p}".format(p=pause))
			except Empty:
				self.logger.verbose("No tasks in queue for {env}".format(
					env=env))
			except (
					requests.exceptions.ConnectionError,
					requests.exceptions.InvalidURL,
					ResponseDecodeError,
					SnowError,
					zeep.exceptions.TransportError
			) as e:
				self.logger.error("SOAP call failed: " + str(e))
				pause += step
				step = step*self.default_factor
				if pause > self.default_limit:
					pause = self.default_limit
					step = 0
				self.logger.debug("Backoff delay increased to {p}".format(p=pause))
			except KeyError:
				self.logger.warning(
					"No SOAPHandler defined for environment: "
					"{env}".format(env=env))
			except Exception as e:
				self.logger.error(
					"SOAP call failed with unknown error:\n"
					+ traceback.format_exc())
				pause += step
				step = step*self.default_factor
				if pause > self.default_limit:
					pause = self.default_limit
					step = 0
				self.logger.debug("Pause increased to {p}".format(p=pause))
			finally:
				self.logger.trace(
					"Current queue store status for {env}:\n{stats}".format(
						env=env,
						stats=self.queue_map[env].stats()))
				gevent.sleep(pause)

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
		return "BatchOpenSnowTicket"
