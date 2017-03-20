import logging, falcon, os, sys
from urllib.parse import urlparse
from configparser import NoSectionError, NoOptionError
from arago.pyconnectit.protocols.rest.plugins.require_json import RequireJSON
from arago.pyconnectit.protocols.rest.plugins.rest_logger import RESTLogger
from arago.pyconnectit.protocols.rest.plugins.json_translator import JSONTranslator
from arago.pyconnectit.protocols.rest.plugins.auth.basic import BasicAuthentication
from arago.pyconnectit.common.delta_store import DeltaStore

from arago.pyconnectit.common.middleware.store_deltas import StoreDeltas

class RESTAPI(object):
	def __init__(self, baseurl, endpoint, middleware=[]):
		self.logger = logging.getLogger('root')
		self.app=falcon.API(middleware=middleware)
		self.app.add_route(
			baseurl.path + '/events/{env}', endpoint)

	@classmethod
	def from_config(cls, adapter_config, environments_config, triggers=[]):
		logger = logging.getLogger('root')
		try:
			os.makedirs(adapter_config['DeltaStore']['data_dir'], mode=0o700, exist_ok=True)
		except OSError as e:
			logger.critical("Can't create data directory: " + e)
			sys.exit(5)
		delta_store_map= {
			env:DeltaStore(
				db_path = os.path.join(adapter_config['DeltaStore']['data_dir'], env),
				max_size = 1024 * 1024 * adapter_config.getint('DeltaStore', 'max_size_in_mb', fallback=1024),
				schemafile = open(environments_config[env]['event_schema'])
			)
			for env
			in environments_config.sections()
		}
		endpoint=Endpoint(triggers, delta_store_map)
		middleware = [
			RequireJSON(),
			JSONTranslator(),
			StoreDeltas([endpoint], delta_store_map)
		]
		try:
			if adapter_config.getboolean('Authentication', 'enabled'):
				middleware.append(BasicAuthentication.from_config(adapter_config['Authentication']))
			else:
				logger.warn("REST API does not require any authentication")
		except (NoSectionError, NoOptionError) as e:
			logger.warn("REST API does not require any authentication")
		except KeyError:
			logger.critical("Authentication enabled but no credentials set")
			sys.exit(5)
		if logger.getEffectiveLevel() <= logger.TRACE:
			middleware.append(RESTLogger())
		baseurl=urlparse(adapter_config['RESTInterface']['base_url'])
		return cls(baseurl, endpoint, middleware=middleware)

class Endpoint(object):
	def __init__(self, triggers, delta_store_map):
		self.logger = logging.getLogger('root')
		self.triggers = triggers
		self.delta_store_map=delta_store_map

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
				resp.context['result'] = self.delta_store_map[env].get_merged(
					event_id)
				resp.status = falcon.HTTP_200
			else:
				resp.context['result'] = self.delta_store_map[env].get_all()
				resp.status = falcon.HTTP_200
		except Exception as e:
			self.logger.debug(e)
			raise

	def on_delete(self, req, resp, env):
		try:
			max_age = int(req.get_param('max_age'))
			self.delta_store_map[env].cleanup(max_age)
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
