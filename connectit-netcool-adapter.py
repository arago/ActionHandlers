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
import sys, os, falcon, json
from docopt import docopt
from urllib.parse import urlparse, urlunparse
import jsonschema, zeep, requests
import datetime
from lxml import etree
from base64 import b64decode

class SOAPLogger(zeep.Plugin):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.logger=logging.getLogger('root')

	def ingress(self, envelope, http_headers, operation):
		self.logger.debug("[TRACE] SOAP data received:\n" + etree.tostring(
			envelope, encoding='unicode', pretty_print=True))
		return envelope, http_headers

	def egress(self, envelope, http_headers, operation, binding_options):
		self.logger.debug(
			"[TRACE] SOAP data sent to {addr}:\n".format(
				addr=binding_options['address']) + etree.tostring(
					envelope, encoding='unicode', pretty_print=True))
		return envelope, http_headers

class RequireJSON(object):
	def process_request(self, req, resp):
		if not req.client_accepts_json:
			raise falcon.HTTPNotAcceptable(
				'This API only supports responses encoded as JSON.')

		if req.method in ('POST', 'PUT'):
			if 'application/json' not in req.content_type:
				raise falcon.HTTPUnsupportedMediaType(
					'This API only supports requests encoded as JSON.')

class RESTLogger(object):
	def __init__(self):
		self.logger = logging.getLogger('root')
	def process_request(self, req, resp):
		#self.logger.debug("")
		self.logger.debug(
			"[TRACE] JSON data received via {op} at {uri}:\n".format(
				op=req.method, uri=req.relative_uri)
			+ json.dumps(
				req.context['doc'],
				sort_keys=True,
				indent=4,
				separators=(',', ': ')))

class JSONTranslator(object):
	def __init__(self):
		self.logger = logging.getLogger('root')

	def process_request(self, req, resp):
		if req.content_length in (None, 0): return

		body = req.stream.read()
		if not body:
			raise falcon.HTTPBadRequest(
				'Empty request body',
				'A valid JSON document is required.')
		try:
			req.context['doc'] = json.loads(body.decode('utf-8'))
		except ValueError:
			self.logger.debug(
				"[TRACE] Malformed data received "
				"via {op} ar {uri}:\n".format(
					op=req.method,uri=req.relative_uri)
				+ body.decode('utf-8')
			)
			raise falcon.HTTPError(
				falcon.HTTP_753,
				'Malformed JSON',
				'Could not decode the request body.')
		except UnicodeDecodeError:
			self.logger.debug(
				"[TRACE] Malformed data received "
				"via {op} ar {uri}:\n".format(
					op=req.method,uri=req.relative_uri)
				+ str(body)
			)
			raise falcon.HTTPError(
				falcon.HTTP_753,
				'Encoding error',
				'Could not decode payload as UTF-8')

	def process_response(self, req, resp, resource):
		if 'result' not in req.context:
			return

		resp.body = json.dumps(req.context['result'])

class AuthMiddleware(object):
	def __init__(self):
		self.logger = logging.getLogger('root')

	def process_request(self, req, resp):
		credentials = req.get_header('Authorization')

		challenges = ['Basic realm="connectit-netcool-adapter"']

		if credentials is None:
			description = ('Please provide an auth token '
						   'as part of the request.')
			raise falcon.HTTPUnauthorized(
				'Auth token required',
				description,
				challenges)
		if not self._credentials_are_valid(credentials):
			description = ('The provided auth token is not valid. '
						   'Please request a new token and try again.')
			raise falcon.HTTPUnauthorized(
				'Authentication required',
				description,
				challenges,
				href='http://docs.example.com/auth')

	def _credentials_are_valid(self, credentials):
		try:
			credentials = b64decode(
				credentials.encode('ascii')[6:]).decode('ascii')
			username, password = tuple(
				falcon.uri.decode(item)
				for item
				in credentials.split(':', 1))
		except Exception:
			self.logger.error(
				"Error decoding authentication credentials!")
			return False
		return username == 'stormking' and password == 'melange'

class RESTAPI(object):
	def __init__(self, baseurl, endpoint):
		self.app=falcon.API(middleware=[
			AuthMiddleware(),
			RequireJSON(),
			JSONTranslator(),
			RESTLogger()
		])
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
			self.soap_interface_map[env].netcool_service.runPolicy(
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
			self.logger.error("SOAP call failed: " + str(e))
		except requests.exceptions.InvalidURL as e:
			self.logger.error("SOAP call failed: " + str(e))
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
		self.logger.debug("New message for environment: {env}".format(
			env=env))
		for trigger in self.triggers:
			trigger(req.context['doc'], env)
		resp.status = falcon.HTTP_200

class ConnectitDaemon(Daemon):
	def run(self):
		config_path = '/opt/autopilot/connectit/conf/'
		main_config_file = os.path.join(
			config_path, 'connectit-netcool-adapter.conf')
		interfaces_config_file = os.path.join(
			config_path, 'connectit-netcool-adapter-netcool.conf')

		share_dir = os.path.join(
			os.getenv('PYTHON_DATADIR'), 'connectit-netcool-adapter')

		# Setup logging in normal operation
		logging.config.fileConfig(os.path.join(
			config_path, 'connectit-netcool-adapter-logging.conf'))
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
		wsdl_file_path = os.path.join(share_dir, 'wsdl', 'netcool.wsdl')
		for env in interfaces_config.sections():
			session = requests.Session()
			session.auth = requests.auth.HTTPBasicAuth(
				interfaces_config[env]['Username'],
				interfaces_config[env]['Password'])
			logger.debug(
				"Loading interface description from {file}".format(
					file=wsdl_file_path))
			soap_client = zeep.Client(
				'file://' + wsdl_file_path,
				transport=zeep.Transport(session=session),
				plugins=[SOAPLogger()]
			)
			logger.debug(
				"Adding Netcool SOAP endpoint for {env} at {ep}".format(
					env=env,
					ep=interfaces_config[env]['Endpoint']))
			soap_client.netcool_service = soap_client.create_service(
				'{http://response.micromuse.com/types}ImpactWebServiceListenerDLIfcBinding', interfaces_config[env]['Endpoint'])
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
				open(os.path.join(
					share_dir, "schemas/event-status-change.json")),
				StatusChange(soap_interfaces_map, status_map)),
			Trigger(
				open(os.path.join(
					share_dir, "schemas/event-comment-added.json")),
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
	args=docopt(__doc__, version='connectit-netcool-adapter 0.2')
	daemon = ConnectitDaemon(args['--pidfile'], debug=args['--debug'])
	if   args['start']:
		daemon.start()
	elif args['stop']:
		daemon.stop()
	elif args['restart']:
		daemon.restart()
	sys.exit(0)
