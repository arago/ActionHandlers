#!/usr/bin/env python
"""connectit-netcool-adapter

Usage:
  connectit-netcool-adapter [options] (start|stop|restart)

Options:
  --debug            do not run as daemon and log to stderr
  --pidfile=PIDFILE  Specify pid file [default: /var/run/{progname}.pid]
  -h --help          Show this help screen
"""
import gevent
from gevent import pywsgi
from gevent import monkey; monkey.patch_all()
import gevent.hub
import signal
from configparser import ConfigParser
import logging, logging.config
from connectit.daemon import Daemon
import sys, falcon, json
from docopt import docopt
from urllib.parse import urlparse, urlunparse
import jsonschema, zeep, requests
import datetime
from lxml import etree

class SOAPLogger(zeep.Plugin):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.logger=logging.getLogger('root')

	def ingress(self, envelope, http_headers, operation):
		self.logger.debug("SOAP data received:\n" + etree.tostring(
			envelope, encoding='unicode', pretty_print=True))
		return envelope, http_headers

	def egress(self, envelope, http_headers, operation, binding_options):
		self.logger.debug("SOAP data sent:\n" + etree.tostring(
			envelope, encoding='unicode', pretty_print=True))
		return envelope, http_headers

class RESTAPI(object):
	def __init__(self, baseurl, endpoint):
		self.app=falcon.API()
		self.baseurl=baseurl
		self.basepath=urlparse(baseurl).path
		self.endpoint = endpoint
		self.app.add_route(
			self.basepath + '/events/{env}', self.endpoint)

class Trigger(object):
	def __init__(self, schemafile, handler):
		self.logger = logging.getLogger('root')
		self.schemafile=schemafile
		self.schema = json.load(schemafile)
		self.handler = handler

	def __call__(self, data, env):
		try:
			jsonschema.validate(data, self.schema)
			self.logger.debug((
				"Schema {s} validated, "
				"calling Handler: {handler}").format(
					s=self.schemafile, handler=self.handler))
			self.handler(data, env)
		except jsonschema.ValidationError:
			self.logger.debug((
				"Schema {s} could not be validated, "
				"ignoring event.").format(s=self.schemafile))

class Handler(object):
	def __init__(self): self.logger = logging.getLogger('root')

class SOAPHandler(Handler):
	def __init__(self, soap_interface_map={}):
		super().__init__()
		self.soap_interface_map=soap_interface_map

class StatusChange(SOAPHandler):
	def __init__(self, soap_interface_map={}, status_map={}):
		super().__init__(soap_interface_map)
		self.status_map = status_map

	def log_status_change(self, env, eventId, status):
		self.logger.info("Status of Event {ev} changed to {st}".format(
			ev=eventId,
			st=status))

	def change_status_in_netcool(self, env, eventId, status):
		try:
			self.soap_interface_map[env].service.runPolicy(
				"get_from_hiro", {
					'desc': "HIRORecieveUpdate",
					'format': "String",
					'label': "HIRO2NETCOOL",
					'name': "HIRO2NETCOOL",
					'value': "{event_id},{status_code}|".format(
						event_id=eventId,
						status_code=self.status_map[status]
					)
				}, True)
		except requests.exceptions.ConnectionError as e:
			self.logger.error("SOAP call failed")
		except KeyError:
			self.logger.warning(
				"No SOAPHandler defined for environment: {env}".format(
					env=env))

	def __call__(self, data, env):
		self.log_status_change(
			env,
			data['mand']['eventId'],
			data['free']['eventNormalizedStatus'])
		self.change_status_in_netcool(
			env,
			data['mand']['eventId'],
			data['free']['eventNormalizedStatus'])

class CommentAdded(SOAPHandler):

	def log_comment(self, env, timestamp, eventId, message):
			self.logger.info((
				"A comment was added to event {ev}"
				" at {time}: {cmt}").format(
					ev=eventId,
					time=datetime.datetime.fromtimestamp(
						timestamp/1000).strftime(
							'%Y-%m-%d %H:%M:%S'),
					cmt=message))

	def add_comment_to_netcool(self, env, timestamp, eventId, message):
			try:
				pass
			except KeyError:
				self.logger.warning((
					"No SOAPHandler defined "
					"for environment: {env}").format(env=env))

	def __call__(self, data, env):
		for comment in sorted(
				data['opt']['comment'],
				key=lambda comment: comment['opt']['timestamp']):
			self.log_comment(
				env,
				int(comment['opt']['timestamp']),
				data['mand']['eventId'],
				comment['opt']['content'])
			self.add_comment_to_netcool(
				env,
				int(comment['opt']['timestamp']),
				data['mand']['eventId'],
				comment['opt']['content'])

class Endpoint(object):
	def __init__(self, triggers):
		self.logger = logging.getLogger('root')
		self.triggers = triggers

	def on_post(self, req, resp, env):
		data = json.loads(req.stream.read().decode("utf-8"))
		#self.logger.trace("Received JSON data:\n" + json.dumps(data,sort_keys=True, indent=4, separators=(',', ': ')))
		self.logger.debug("New message for environment: {env}".format(
			env=env))
		for trigger in self.triggers:
			trigger(data, env)
		resp.status = falcon.HTTP_200

class ConnectitDaemon(Daemon):
	def run(self):
		config_path = '/opt/autopilot/connectit/conf/'
		main_config_file = (
			'{path}/connectit-netcool-adapter.conf'
		).format(path=config_path)
		interfaces_config_file = (
			'{path}/connectit-netcool-adapter-netcool.conf'
		).format(path=config_path)

		# Setup logging in normal operation
		logging.config.fileConfig((
			'{path}/connectit-netcool-adapter-logging.conf'
		).format(path=config_path))
		logger = logging.getLogger('root')

		# Setup debug logging
		if self.debug:
			logger.setLevel(logging.DEBUG)
			ch = logging.StreamHandler()
			ch.setLevel(logging.DEBUG)
			formatter = logging.Formatter(
				"%(asctime)s [%(levelname)s] %(message)s",
				"%Y-%m-%d %H:%M:%S")
			ch.setFormatter(formatter)
			logger.addHandler(ch)
			logger.info("Logging to console and logfile")

		logger.info("HIRO Connect Netcool Adapter starting up ...")
		logger.debug("Reading main config file {file}".format(
			file=main_config_file))
		adapter_config=ConfigParser()
		adapter_config.read(main_config_file)

		logger.debug("Reading config file {file}".format(
			file=interfaces_config_file))
		interfaces_config=ConfigParser()
		interfaces_config.read(interfaces_config_file)

		rest_url = urlparse(
			adapter_config.get('RESTInterface', 'BaseURL'))
		logger.debug("Setting up REST interface at {url}".format(
			url=urlunparse(rest_url)))

		soap_interfaces_map = {}
		for env in interfaces_config.sections():
			logger.debug(
				"Adding Netcool SOAP endpoint for {env} at {ep}".format(
					env=env,
					ep=interfaces_config[env]['Endpoint']))
			session = requests.Session()
			session.auth = requests.auth.HTTPBasicAuth(
				interfaces_config[env]['Username'],
				interfaces_config[env]['Password'])
			soap_client = zeep.Client(
				'file://data/netcool.wsdl',
				transport=zeep.Transport(session=session),
				plugins=[SOAPLogger()]
			)
			soap_interfaces_map[env]=soap_client

		status_map = {
			"New":3001,
			"Assigned":3002,
			"Pending":3006,
			"Resolved":3003,
			"Escalated":3004,
			"Closed":3005
		}

		triggers= [
			Trigger(
				open("schemas/event-status-change.json"),
				StatusChange(soap_interfaces_map, status_map)),
			Trigger(
				open("schemas/event-comment-added.json"),
				CommentAdded(soap_interfaces_map))
		]
		server = pywsgi.WSGIServer(
			(rest_url.hostname, rest_url.port),
			RESTAPI(
				rest_url.path,
				Endpoint(triggers)
			).app,
			log=None,
			error_log=logger)
		def exit_gracefully():
			logger.info("Shutting down ...")
			server.stop()
			logger.debug("Shutdown complete!")
			sys.exit(0)
		gevent.hub.signal(signal.SIGINT, exit_gracefully)
		gevent.hub.signal(signal.SIGTERM, exit_gracefully)
		logger.debug("Starting server ...")
		server.serve_forever()


if __name__ == "__main__":

	args=docopt(__doc__, version='connectit-netcool-adapter 0.1')
	daemon = ConnectitDaemon(args['--pidfile'], debug=args['--debug'])
	if   args['start']:   daemon.start()
	elif args['stop']:    daemon.stop()
	elif args['restart']: daemon.restart()
	sys.exit(0)
