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
import datetime, time
from lxml import etree
from base64 import b64decode
import lmdb
import jsonmerge
import functools


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
		indent=4,
		separators=(',', ': '))

class DeltaStore(object):
	def __init__(self, db_path, max_size, schemafile):
		self.logger = logging.getLogger('root')
		self.lmdb_env_main = lmdb.open(
			os.path.join(db_path, "main"),
			map_size=max_size*95/100,
			subdir=False,
			max_dbs=10,
			writemap=True,
			max_readers=16,
			max_spare_txns=10)
		self.lmdb_env_ts = lmdb.open(
			os.path.join(db_path, "timestamps"),
			map_size=max_size*5/100,
			subdir=False,
			max_dbs=10,
			writemap=True,
			max_readers=16,
			max_spare_txns=10)
		self.logger.debug(
			"[LMDB] db = env.open_db(dupsort=True, dupfixed=False)")
		self.db_main = self.lmdb_env_main.open_db(
			dupsort=True, dupfixed=False)
		self.db_ts = self.lmdb_env_ts.open_db()
		self.merger = jsonmerge.Merger(json.load(schemafile))
	def close(self):
		self.lmdb_env_main.close()
		self.lmdb_env_ts.close()
	def merge(self, base, delta):
		base = json.loads(base.decode('utf-8'))
		delta = json.loads(delta.decode('utf-8'))
		result = self.merger.merge(base, delta)
		return json.dumps(result).encode('utf-8')
	def get_merged(self, key):
		with self.lmdb_env_main.begin(db=self.db_main) as txn:
			with txn.cursor() as cursor:
				return cursor.get(key.encode('utf-8'))
		# 		cursor.set_key(key.encode('utf-8'))
		# 		try:
		# 			self.logger.debug("Found {num} deltas".format(
		# 			num=cursor.count()))
		# 		except:
		# 			pass
		# 		result = functools.reduce(
		# 			self.merge, cursor.iternext_dup())
		# return result
	def get_all(self):
		with self.lmdb_env_main.begin(db=self.db_main) as txn:
			with txn.cursor() as cursor:
				cursor.first()
				for key, value in cursor.iternext(keys=True, values=True):
					self.logger.debug("{k}:{v}".format(
						k=key.decode('utf-8'),
						v=value.decode('utf-8')
					))
		return b'{}'
	def append(self, key, delta):
		with self.lmdb_env_main.begin(
				db=self.db_main, write=True) as txn_main:
			with self.lmdb_env_ts.begin(db=self.db_ts,
										write=True) as txn_ts:
				ts = time.time()
				try:
					base = txn_main.get(key=key.encode('utf-8'))
					ref = delta.encode('utf-8')
					merged = self.merge(base, ref)
				except Exception as e:
					self.logger.debug(e)
					merged = delta.encode('utf-8')
				txn_main.put(
					key=key.encode('utf-8'),
					value=merged,
					dupdata=True)
				txn_ts.put(
					key=key.encode('utf-8'),
					value = str(ts).encode('utf-8'),
					overwrite=True
				) # Think about optimization!

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
		if 'doc' in req.context:
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
	def __init__(self, baseurl, endpoint, config):
		self.app=falcon.API(middleware=[
			RequireJSON(),
			JSONTranslator(),
			RESTLogger(),
			#AuthMiddleware(config)
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
	def __init__(self, soap_interface_map={}, delta_store_map={}):
		super().__init__(soap_interface_map)
		self.delta_store_map = delta_store_map

	def log_comment(self, env, timestamp, eventId, message):
			self.logger.info((
				"A comment was added to event {ev}"
				" at {time}: {cmt}").format(
					ev=eventId,
					time=datetime.datetime.fromtimestamp(
						timestamp/1000).strftime(
							'%Y-%m-%d %H:%M:%S'),
					cmt=message))

	def store_delta(self, env, eventId, data):
		try:
			self.delta_store_map[env].append(eventId, json.dumps(data))
		except KeyError:
			self.logger.warning(
				"No DeltaStore defined for environment: {env}".format(
					env=env))

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
			self.store_delta(
				env,
				data['mand']['eventId'],
				data)
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

class StatusEjected(SOAPHandler):
	def __init__(self, delta_store_map, soap_interfaces_map, status_map):
		super().__init__(soap_interfaces_map)
		self.delta_store_map = delta_store_map
	def get_status(self, data):
		return data['free']['eventNormalizedStatus']
	def get_comments(self, env, eventId):
		return json.loads(self.delta_store_map[env].get_merged(eventId).decode('utf-8'))['opt']['comment']
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
				notes="\n".join(["[{ts}] {body}".format(ts=comment['timestamp'], body=comment['content']) for comment in comments]),
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

	def on_get(self, req, resp, env):
		try:
			event_id=req.get_param('id')
			if event_id:
				resp.context['result'] = json.loads(self.store[env].get_merged(event_id).decode('utf-8'))
			else:
				resp.context['result'] = json.loads(self.store[env].get_all().decode('utf-8'))
		except Exception as e:
			self.logger.debug(e)
			raise

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
		try:
			logging.config.fileConfig(os.path.join(
				config_path, 'connectit-netcool-adapter-logging.conf'))
		except Exception as e:
			print(e, file=sys.stderr)
			sys.exit(5)
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
		snow_wsdl_file_path = os.path.join(share_dir, 'wsdl', 'snow.wsdl')
		db_path = '/tmp/testdb'
		delta_store_map={}
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
			try:
				os.makedirs(
					os.path.join(db_path, env),
					mode=0o700, exist_ok=True)
			except OSError as e:
				self.logger.critical("Can't create data directory: " + e)
				sys.exit(5)

			delta_store_map[env]=DeltaStore(
				db_path = os.path.join(db_path, env),
				max_size = 1024*1024*100,
				schemafile = open(os.path.join(
					share_dir, "schemas/event-comment-added.json")))

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
		logger.debug("[LMDB] env = lmdb.open(\"/tmp/delta_store\", map_size=1048576000, max_dbs=10, writemap=True, max_readers=16, max_spare_txns=10)")

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
		server = pywsgi.WSGIServer(
			(rest_url.hostname, rest_url.port),
			RESTAPI(
				rest_url.path,
				Endpoint(triggers, delta_store_map),
				config=adapter_config
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
