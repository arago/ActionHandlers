import zeep
from requests.exceptions import ConnectionError
from zeep.exceptions import TransportError
from docopt import docopt
import shlex
import json
import logging
import traceback
from pyactionhandler import Action
from pyactionhandler.ayehu.exceptions import ResourceNotExistsError

class AyehuAction(Action):
	def __init__(self, num, node, zmq_info, timeout, parameters,
				 zeep_transport, redis, ayehu_config, pmp_config,
				 rest_api):
		super(AyehuAction, self).__init__(
			num, node, zmq_info, timeout, parameters)
		self.logger = logging.getLogger('root')
		self.redis=redis
		self.ayehu_config=ayehu_config
		self.pmp_config=pmp_config
		self.rest_api=rest_api
		self.customer = parameters['CustomerID'] if 'CustomerID' in parameters else 'default'
		try:
			self.zeep_client = zeep.Client(
				ayehu_config.get(self.customer, 'URL'),transport=zeep_transport)
		except ConnectionError as e:
			self.logger.error("[{anum}] Error connecting to Ayehu!".format(anum=num))
			self.logger.debug("[{anum}] Error message was: {err}".format(
				anum=self.num,
				err=str(e)))
			raise
		except Exception as e:
			self.logger.debug(e)
			self.logger.error("Error initializing Ayehu SOAP client!\n{tb}".format(
				tb=traceback.format_exc()))
		try:
			command_usage="""
Usage:
  Keyword: <command> [(<param> = <val>)]...
"""
			argv=shlex.split(parameters['Command'])
			args=docopt(command_usage, argv=argv)
			self.info = {
				'DeviceID':parameters['Hostname'],
				'TaskKeywords':args['<command>'],
				'Parameters':dict(zip(args['<param>'], args['<val>'])),
				'Customer':parameters['CustomerID'],
				'ServiceAccount':parameters['ServiceAccount'],
				'PMPServer':self.pmp_config.get(
					self.customer, 'URL'),
				'IncidentID':parameters['Ticket'],
				'CallbackURL':"{baseurl}/commands/{{id}}".format(
					baseurl=self.rest_api.baseurl)
			}
		except Exception as e:
			self.logger.warning(
				"[{anum}] Error parsing command '{cmd}': {err}".format(
					anum=self.num, cmd=self.parameters['Command'], err=e))

	def __timeout__(self, seconds):
		self.rest_api.command.delete(self.cmdid)

	def __shutdown__(self):
		self.rest_api.command.delete(self.cmdid)

	def __str__(self):
		return "Ayehu command '{cmd}' on '{node}'".format(
			cmd=self.parameters['Command'],
			node=self.node)

	def __call__(self):
		# pubsub object must be greenlet-local
		self.pubsub=self.redis.pubsub(ignore_subscribe_messages=True)

		# process action
		self.create_rest_resource()
		self.open_incident()
		self.wait_for_rest_callback()

	def open_incident(self):
		self.info['CallbackURL'] = self.info['CallbackURL'].format(
			id=self.cmdid)
		try:
			operation = self.ayehu_config.get(self.customer, 'Method', fallback='incident')
			self.logger.debug("[{anum}] Calling Ayehu using SOAP Operation: {op}".format(
				anum=self.num, op=operation))
			if operation == 'email':
				self.zeep_client.service.EyeShareWebService_Email_Format(
					self.ayehu_config.get(self.customer, 'EyeshareIP'),
					self.ayehu_config.get(self.customer, 'Source'),
					self.info['DeviceID'],
					self.parameters['Ticket'], # Subject
					json.dumps(self.info), # Message
					'' # HTMLMessage
				)
			elif operation == 'generic':
				self.zeep_client.service.EyeShareWebService_Generic(
					self.ayehu_config.get(self.customer, 'Source'),
					json.dumps(self.info),
					False)
			else: # operation == 'incident' and fallback for unknown methods
				self.zeep_client.service.EyeShareWebService_Incident_Format(
					self.ayehu_config.get(self.customer, 'EyeshareIP'),
					self.ayehu_config.get(self.customer, 'Source'),
					self.info['DeviceID'],
					self.parameters['Classification'],
					json.dumps(self.info),
					self.ayehu_config.get(self.customer, 'State'),
					self.ayehu_config.get(self.customer, 'Severity'))
		except (TransportError, ConnectionError) as e:
			self.rest_api.command.delete(self.cmdid)
			self.logger.error("[{anum}] Error when creating incident in Ayehu: {err}".format(
				anum=self.num, err=e))

	def create_rest_resource(self):
		self.cmdid = self.rest_api.collection.post(self.info)
		self.pubsub.psubscribe(self.cmdid)

	def wait_for_rest_callback(self):
		for message in self.pubsub.listen():
			if message['data'] == 'exit':
				try:
					self.output="\n".join(
						self.rest_api.stdout.get(self.cmdid))
				except ResourceNotExistsError:
					self.output=""
				try:
					self.error_output="\n".join(
						self.rest_api.stderr.get(self.cmdid))
				except ResourceNotExistsError:
					self.error_output=""
				self.system_rc = self.rest_api.props.get(
					self.cmdid, 'rc') or 0
				self.rest_api.command.delete(self.cmdid)
				self.success=True
				return
