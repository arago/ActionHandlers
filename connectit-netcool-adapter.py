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
from gevent import monkey; monkey.patch_all(sys=True)
import gevent.hub, gevent.queue
import signal
from configparser import ConfigParser
import logging, logging.config
from connectit.daemon import Daemon
import sys, os, falcon
import ujson as json
from docopt import docopt
from urllib.parse import urlparse, urlunparse
import jsonschema, zeep, requests
import fastjsonschema
import datetime, time
from lxml import etree
from base64 import b64decode
import lmdb
import jsonmerge
import functools
import itertools
from lz4 import compress, uncompress


def prettify(data):
	try:
		data = data.decode('utf-8')
	except:
		pass
	try:
		data=json.loads(data)
	except:
		pass
	return json.dumps(
		data,
		sort_keys=True,
		indent=4)

class DeltaStore(object):
	def __init__(self, db_path, max_size, schemafile):
		self.logger = logging.getLogger('root')
		self.lmdb = lmdb.open(
			db_path,
			map_size=max_size,
			subdir=False,
			max_dbs=5,
			writemap=True,
			# metasync=False,
			# sync=False,
			# map_async=True,
			max_readers=16,
			max_spare_txns=10)
		self.index_name = 'index'.encode('utf-8')
		self.deltas_name = 'deltas'.encode('utf-8')
		self.mtimes_name = 'mtimes'.encode('utf-8')
		with self.lmdb.begin(write=True) as txn:
			self.lmdb.open_db(
				key=self.index_name, txn=txn, dupsort=True)
			self.lmdb.open_db(
				key=self.mtimes_name, txn=txn)
			self.lmdb.open_db(
				key=self.deltas_name, txn=txn)
		self.delta_idx = self.get_delta_idx()
		self.merger = jsonmerge.Merger(json.load(schemafile))

	def get_delta_idx(self):
		with self.lmdb.begin() as txn:
			deltas_db = self.lmdb.open_db(
				key=self.deltas_name, txn=txn)
			with txn.cursor(db=deltas_db) as cursor:
				return itertools.count(
					start=int.from_bytes(
						cursor.key(),
						byteorder=sys.byteorder,
						signed=False)  + 1,
						step=1
				) if cursor.last() else itertools.count(
					start=1, step=1)
	def delete(self, eventId):
		with self.lmdb.begin(write=True) as txn:
			index_db = self.lmdb.open_db(
				key=self.index_name, txn=txn, dupsort=True)
			mtimes_db = self.lmdb.open_db(
				key=self.mtimes_name, txn=txn)
			deltas_db = self.lmdb.open_db(
				key=self.deltas_name, txn=txn)
			self.logger.debug(("Removing Event {ev} from the "
							   "database").format(ev=eventId))
			with txn.cursor(db=index_db) as cursor:
				cursor.set_key(eventId.encode('utf-8'))
				self.logger.debug("Found {n} deltas".format(
					n = cursor.count()))
				for delta_key in cursor.iternext_dup(keys=False):
					data = txn.get(delta_key, db=deltas_db)
					self.logger.debug("Deleting delta {id}\n".format(
						id=delta_key.decode('utf-8'))
									  + prettify(data))
					txn.delete(delta_key, db=deltas_db)
			self.logger.debug("Deleting MTIME")
			txn.delete(eventId.encode('utf-8'), db=mtimes_db)
			self.logger.debug("Deleting index entry")
			txn.delete(eventId.encode('utf-8'), db=index_db)
	def cleanup(self, max_age):
		with self.lmdb.begin() as txn:
			mtimes_db = self.lmdb.open_db(
				key=self.mtimes_name, txn=txn)
			with txn.cursor(db=mtimes_db) as cursor:
				if cursor.first():
					for eventId, timestamp in cursor.iternext(
							keys=True, values=True):
						age = int(time.time() * 1000) - int.from_bytes(
							timestamp,
							byteorder=sys.byteorder,
							signed=False)
						eventId = eventId.decode('utf-8')
						self.logger.debug(
							("Event {ev} was last updated {s} "
							 "milliseconds ago.").format(
								 ev = eventId, s = age))
						if age >= max_age * 1000:
							self.delete(eventId)

	def append(self, eventId, data):
		with self.lmdb.begin(write=True) as txn:
			eventId = eventId.encode('utf-8')
			data = compress(json.dumps(data))
			mtime = int(time.time() * 1000).to_bytes(
				length=6,
				byteorder=sys.byteorder,
				signed=False)
			delta_idx = next(self.delta_idx).to_bytes(
				length=511,
				byteorder=sys.byteorder,
				signed=False)
			index_db = self.lmdb.open_db(
				key=self.index_name, txn=txn, dupsort=True)
			mtimes_db = self.lmdb.open_db(
				key=self.mtimes_name, txn=txn)
			deltas_db = self.lmdb.open_db(
				key=self.deltas_name, txn=txn)
			txn.put(delta_idx, data, append=True, db=deltas_db)
			txn.put(eventId, delta_idx, dupdata=True, db=index_db)
			txn.put(eventId, mtime, overwrite=True, db=mtimes_db)
	def get_merged(self, eventId):
		with self.lmdb.begin() as txn:
			eventId = eventId.encode('utf-8')
			index_db = self.lmdb.open_db(
				key=self.index_name, txn=txn, dupsort=True)
			deltas_db = self.lmdb.open_db(
				key=self.deltas_name, txn=txn)
			with txn.cursor(db=index_db) as cursor:
				result = {}
				if cursor.set_key(eventId):
					for delta in cursor.iternext_dup():
						result = self.merger.merge(
							result,
							json.loads(uncompress(txn.get(
								delta, db=deltas_db))),
							meta={'timestamp': str(int(time.time()*1000))}
						)
				return result

class SOAPLogger(zeep.Plugin):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.logger=logging.getLogger('root')

	def ingress(self, envelope, http_headers, operation):
		self.logger.trace("SOAP data received:\n" + etree.tostring(
			envelope, encoding='unicode', pretty_print=True))
		return envelope, http_headers

	def egress(self, envelope, http_headers, operation, binding_options):
		self.logger.trace(
			"SOAP data sent to {addr}:\n".format(
				addr=binding_options['address']) + etree.tostring(
					envelope, encoding='unicode', pretty_print=True))
		return envelope, http_headers

class RequireJSON(object):
	def __init__(self):
		self.logger = logging.getLogger('root')
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
		if 'doc' in req.context:
			self.logger.trace(
				"JSON data received via {op} at {uri}:\n".format(
					op=req.method, uri=req.relative_uri)
				+ prettify(req.context['doc'])
				)

class StoreDeltas(object):
	def __init__(self, resources, delta_store_map):
		self.logger = logging.getLogger('root')
		self.resources = resources
		self.delta_store_map = delta_store_map
	def process_resource(self, req, resp, resource, params):
		if 'doc' in req.context and resource in self.resources:
			try:
				self.delta_store_map[params['env']].append(
					req.context['doc']['mand']['eventId'],
					req.context['doc']
				)
			except KeyError:
				self.logger.warning(
					"No DeltaStore defined for environment: {env}".format(
						env=params['env']))

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
			self.logger.trace(
				"Malformed data received "
				"via {op} ar {uri}:\n".format(
					op=req.method,uri=req.relative_uri)
				+ body.decode('utf-8')
			)
			raise falcon.HTTPError(
				falcon.HTTP_753,
				'Malformed JSON',
				'Could not decode the request body.')
		except UnicodeDecodeError:
			self.logger.trace(
				"Malformed data received "
				"via {op} ar {uri}:\n".format(
					op=req.method,uri=req.relative_uri)
				+ str(body)
			)
			raise falcon.HTTPError(
				falcon.HTTP_753,
				'Encoding error',
				'Could not decode payload as UTF-8')

	def process_response(self, req, resp, resource):
		if 'result' not in resp.context:
			return

		resp.body = json.dumps(resp.context['result'])

class AuthMiddleware(object):
	def __init__(self, auth_config):
		self.username = auth_config.get('Authentication', 'Username')
		self.password = auth_config.get('Authentication', 'Password')
		self.logger = logging.getLogger('root')

	def process_request(self, req, resp):
		credentials = req.get_header('Authorization')

		challenges = ['Basic realm="connectit-netcool-adapter"']

		if credentials is None:
			description = ('Please provide authentication '
						   'credentials as part of the request.')
			raise falcon.HTTPUnauthorized(
				'Auth token required',
				description,
				challenges)
		if not self._credentials_are_valid(credentials):
			description = ('The provided credentials are not valid. '
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
			self.logger.debug(username + ":" + self.username)
			self.logger.debug(password + ":" + self.password)
		except Exception:
			self.logger.error(
				"Error decoding authentication credentials!")
			return False
		return username == self.username and password == self.password

class RESTAPI(object):
	def __init__(self, baseurl, endpoint, config, delta_store_map):
		self.logger = logging.getLogger('root')
		self.middleware = [
			RequireJSON(),
			JSONTranslator(),
			StoreDeltas([endpoint], delta_store_map),
			#AuthMiddleware(config)
		]
		if self.logger.getEffectiveLevel() <= self.logger.TRACE:
			self.middleware.append(RESTLogger())
		self.app=falcon.API(middleware=self.middleware)
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

class FastTrigger(Trigger):
	def __init__(self, schemafile, handler):
		super().__init__(schemafile, handler)
		self.validator = fastjsonschema.compile(self.schema)

	def __call__(self, data, env):
		try:
			self.validator(data)
			self.logger.debug((
				"Schema {s} validated, "
				"calling Handler: {handler}").format(
					s=self.schemafile, handler=self.handler))
			self.handler(data, env)
		except fastjsonschema.JsonSchemaException:
			self.logger.debug((
				"Schema {s} could not be validated, "
				"ignoring event.").format(s=self.schemafile))

class Handler(object):
	def __init__(self):
		self.logger = logging.getLogger('root')

class SOAPHandler(Handler):
	def __init__(self, soap_interface_map={}):
		super().__init__()
		self.soap_interface_map=soap_interface_map

class StatusChange(SOAPHandler):
	def __init__(self, soap_interface_map={}, status_map={}):
		super().__init__(soap_interface_map)
		self.status_map = status_map

	def log_status_change(self, env, eventId, status):
		self.logger.verbose("Status of Event {ev} changed to {st}".format(
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
	def __init__(self, soap_interface_map={}, delta_store_map={}):
		super().__init__(soap_interface_map)
		self.delta_store_map = delta_store_map

	def log_comment(self, env, timestamp, eventId, message):
			self.logger.verbose((
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

class Noop(object):
	def __init__(self):
		self.logger = logging.getLogger('root')
	def __call__(self, data, env):
		pass

class StatusEjected(SOAPHandler):
	def __init__(self, delta_store_map, soap_interfaces_map, status_map):
		super().__init__(soap_interfaces_map)
		self.delta_store_map = delta_store_map
	def get_status(self, data):
		return data['free']['eventNormalizedStatus']
	def get_comments(self, env, eventId):
		return self.delta_store_map[env].get_merged(
			eventId)['opt']['comment']
	def open_ticket_in_snow(self, env, eventId, status, comments=[]):
		try:
			result = self.soap_interface_map[env].snow_service.execute(
				UBStable="incident",
				UBSaction="create",
				system="",
				summary="",
				details="",
				netcool_id=eventId,
				arago_id=eventId,
				notes="\n".join(["[{ts}] {body}".format(
					ts=comment['timestamp'],
					body=comment['content']
				) for comment in comments]),
				tranasction_time=datetime.datetime.now().strftime(
					'%Y-%m-%d %H:%M:%S')
				)
			self.logger.debug(result)
		except requests.exceptions.ConnectionError as e:
			self.logger.error("SOAP call failed: " + str(e))
		except requests.exceptions.InvalidURL as e:
			self.logger.error("SOAP call failed: " + str(e))
		except KeyError:
			self.logger.warning(
				"No SOAPHandler defined for environment: {env}".format(
					env=env))
	def __call__(self, data, env):
		status = self.get_status(data)
		comments = [item['opt'] for item in self.get_comments(
			env,
			data['mand']['eventId']
		)]
		self.open_ticket_in_snow(
			env,
			data['mand']['eventId'],
			status,
			comments
		)
		self.logger.debug(status)
		for comment in comments:
			self.logger.debug(comment['content'])

class Endpoint(object):
	def __init__(self, triggers, store):
		self.logger = logging.getLogger('root')
		self.triggers = triggers
		self.store=store

	def on_post(self, req, resp, env):
		self.logger.debug("New message for environment: {env}".format(
			env=env))
		for trigger in self.triggers:
			trigger(req.context['doc'], env)
		resp.status = falcon.HTTP_200

	def on_delete(self, req, resp, env):
		try:
			max_age = int(req.get_param('max_age'))
			self.store[env].cleanup(max_age)
			resp.status = falcon.HTTP_200
		except TypeError as e:
			self.logger.warning(e)
			raise falcon.HTTPBadRequest(
				'Required parameter missing',
				'This operation requires the max_age parameter to be set')
		except ValueError as e:
			self.logger.warning(e)
			raise falcon.HTTPBadRequest(
				'Wrong data',
				'Parameter max_age must be a number (of seconds)')

	def on_get(self, req, resp, env):
		try:
			event_id=req.get_param('id')
			if event_id:
				resp.context['result'] = self.store[env].get_merged(
					event_id)
				resp.status = falcon.HTTP_200
			else:
				resp.context['result'] = self.store[env].get_all()
				resp.status = falcon.HTTP_200
		except Exception as e:
			self.logger.debug(e)
			raise

class Logger(logging.getLoggerClass()):
	CRITICAL=50
	ERROR=40
	WARNING=30
	INFO=20
	VERBOSE=15
	DEBUG=10
	TRACE= 5
	NOTSET=0
	def __init__(self, name, level=logging.NOTSET):
		super().__init__(name, level)
		logging.addLevelName(self.VERBOSE, "VERBOSE")
		logging.addLevelName(self.TRACE, "TRACE")
	def verbose(self, msg, *args, **kwargs):
		if self.isEnabledFor(self.VERBOSE):
			self._log(self.VERBOSE, msg, args, **kwargs)
	def trace(self, msg, *args, **kwargs):
		if self.isEnabledFor(self.TRACE):
			self._log(self.TRACE, msg, args, **kwargs)

class TimeoutMemoryHandler(logging.handlers.MemoryHandler):
	def __init__(self, capacity, flushLevel=logging.ERROR,
				 target=None, timeout=10):
		super().__init__(capacity, flushLevel, target)
		self.timeout=timeout
		gevent.spawn(self.flushOnTimeout)

	def flushOnTimeout(self):
		while True:
			gevent.sleep(self.timeout)
			self.flush()

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

		logging.setLoggerClass(Logger)
		logger = logging.getLogger('root')
		logger.setLevel(logger.INFO)

		logfile_formatter = logging.Formatter(
			"%(asctime)s [%(levelname)s] %(message)s",
			"%Y-%m-%d %H:%M:%S")

		logfile_handler = logging.FileHandler(
			'/var/log/autopilot/connectit/netcool-adapter.log')
		logfile_handler.setFormatter(logfile_formatter)

		mem_handler = TimeoutMemoryHandler(
			10000, target=logfile_handler,
			flushLevel=logger.CRITICAL, timeout=5)
		logfile_handler.setLevel(logging.INFO)
		mem_handler.setLevel(logging.INFO)
		logger.addHandler(mem_handler)

		# Setup debug logging
		if self.debug:
			stream_handler = logging.StreamHandler()
			stream_handler.setLevel(logger.TRACE)
			debug_formatter = logging.Formatter(
				"[%(levelname)s] %(message)s")
			stream_handler.setFormatter(debug_formatter)
			logger.setLevel(logger.TRACE)
			logger.info("Logging to console and logfile")

			debug_mem_handler = TimeoutMemoryHandler(
				10000, target=stream_handler,
				flushLevel=logger.CRITICAL, timeout=1)
			debug_mem_handler.setLevel(logger.TRACE)
			logger.addHandler(debug_mem_handler)

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
		snow_wsdl_file_path = os.path.join(share_dir, 'wsdl', 'snow.wsdl')
		db_path = '/tmp/testdb'
		delta_store_map={}
		for env in interfaces_config.sections():
			session = requests.Session()
			session.auth = requests.auth.HTTPBasicAuth(
				interfaces_config[env]['Username'],
				interfaces_config[env]['Password']
			)
			logger.debug(
				"Loading interface description from {file}".format(
					file=wsdl_file_path))
			plugins=[]
			if logger.getEffectiveLevel() <= logger.TRACE:
				plugins.append(SOAPLogger())
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
				'{http://response.micromuse.com/types}'
				'ImpactWebServiceListenerDLIfcBinding',
				interfaces_config[env]['Endpoint'])
			soap_interfaces_map[env]=soap_client
			try:
				os.makedirs(db_path, mode=0o700, exist_ok=True)
			except OSError as e:
				self.logger.critical("Can't create data directory: " + e)
				sys.exit(5)

			delta_store_map[env]=DeltaStore(
				db_path = os.path.join(db_path, env),
				max_size = 1024 * 1024 * 2048,
				schemafile = open(os.path.join(
					share_dir, "schemas/event.json")))

		session = requests.Session()
		session.auth = requests.auth.HTTPBasicAuth(
			'FR28981',
			'password')
		snow_soap_client = zeep.Client(
				'file://' + snow_wsdl_file_path,
				transport=zeep.Transport(session=session),
				plugins=[SOAPLogger()]
			)
		snow_soap_client.snow_service = snow_soap_client.create_service(
			'{http://www.service-now.com/UBSTask}ServiceNowSoap',
			'https://gsnowdev.ubsdev.net/webservices/UBSTask.do?SOAP')
		snow_soap_int_map={"DEV":snow_soap_client}

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
				CommentAdded(soap_interfaces_map, delta_store_map)),
			Trigger(
				open(os.path.join(
					share_dir, "schemas/event-status-ejected.json")),
				StatusEjected(
					delta_store_map,
					snow_soap_int_map,
					status_map))
		]

		triggers= [
			FastTrigger(
				open(os.path.join(
					share_dir, "schemas/event-status-change.json")),
				StatusChange(soap_interfaces_map, status_map)),
			FastTrigger(
				open(os.path.join(
					share_dir, "schemas/event-comment-added.json")),
				CommentAdded(soap_interfaces_map, delta_store_map)),
			FastTrigger(
				open(os.path.join(
					share_dir, "schemas/event-status-ejected.json")),
				StatusEjected(
					delta_store_map,
					snow_soap_int_map,
					status_map))
		]
		server = pywsgi.WSGIServer(
			(rest_url.hostname, rest_url.port),
			RESTAPI(
				rest_url.path,
				Endpoint(triggers, delta_store_map),
				config=adapter_config,
				delta_store_map=delta_store_map
			).app,
			log=None,
			error_log=logger)
		def exit_gracefully():
			logger.info("Shutting down ...")
			server.stop()
			logger.debug("Shutdown complete!")
			mem_handler.flush()
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
