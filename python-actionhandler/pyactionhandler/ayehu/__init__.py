import gevent
import zeep
from requests.exceptions import ConnectionError
from zeep.exceptions import TransportError
import redis
from docopt import docopt
import shlex
import json
import uuid
import greenlet

from pyactionhandler import Action

from pyactionhandler.ayehu.exceptions import AyehuAHError, ExitTwiceError, ResourceNotExistsError

class AyehuAction(Action):
	def __init__(self, node, zmq_info, timeout, parameters,
				 zeep_client, redis, ayehu_config, pmp_config,
				 rest_api):
		super(AyehuAction, self).__init__(
			node, zmq_info, timeout, parameters)
		self.zeep_client=zeep_client
		self.redis=redis
		self.ayehu_config=ayehu_config
		self.pmp_config=pmp_config
		self.rest_api=rest_api
		self.baseurl=self.ayehu_config.get('default', 'CallbackBaseURL')
		try:
			command_usage=u"""
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
				'ServiceAccount':parameters['User'],
				'PMPServer':self.pmp_config.get(
					'default', 'URL'),
				'IncidentID':parameters['Ticket'],
				'CallbackURL':"{baseurl}/commands/{{id}}".format(
					baseurl=self.baseurl)
			}
		except Exception as e:
			print (e)

	def __timeout__(self, seconds):
		self.rest_api.command.delete(self.cmdid)

	def __shutdown__(self):
		self.rest_api.command.delete(self.cmdid)

	def __call__(self):
		print("Executing command '{task}' on {node}".format(
			task=self.info['TaskKeywords'], node=self.info['DeviceID']))
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
			self.zeep_client.service.EyeShareWebService_Incident_Format(
				self.ayehu_config.get('default', 'EyeshareIP'),
				self.ayehu_config.get('default', 'Source'),
				self.info['DeviceID'],
				self.parameters['Classification'],
				json.dumps(self.info),
				self.ayehu_config.get('default', 'State'),
				self.ayehu_config.get('default', 'Severity'))
		except TransportError as e:
			self.rest_api.command.delete(self.cmdid)
			print (e)
		except ConnectionError as e:
			self.rest_api.command.delete(self.cmdid)
			print (e)

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
					pass
				try:
					self.error_output="\n".join(
						self.rest_api.stderr.get(self.cmdid))
				except ResourceNotExistsError:
					pass
				self.system_rc = self.rest_api.props.get(
					self.cmdid, 'rc') or 0
				self.rest_api.command.delete(self.cmdid)
				self.success=True
				return

class AyehuBackgroundAction(Action):
	pass
