import logging, falcon, sys
from urllib.parse import urlparse
from configparser import NoSectionError, NoOptionError
from arago.pyconnectit.common.rest.plugins.require_json import RequireJSON
from arago.pyconnectit.common.rest.plugins.rest_logger import RESTLogger
from arago.pyconnectit.common.rest.plugins.restrict_environment import RestrictEnvironment
from arago.pyconnectit.common.rest.plugins.json_translator import JSONTranslator
from arago.pyconnectit.common.rest.plugins.auth.basic import BasicAuthentication
from arago.pyconnectit.common.rest.plugins.store_deltas import StoreDeltas
from arago.pyconnectit.common.lmdb_queue import Empty
from arago.pyconnectit.connectors.netcool.handlers.sync_netcool_status import QueuingError

class RESTAPI(object):
	def __init__(self, baseurl, endpoint, middleware=[]):
		self.logger = logging.getLogger('root')
		self.app=falcon.API(middleware=middleware)
		self.app.add_route(
			baseurl.path + '/events/{env}', endpoint)

	@classmethod
	def from_config(cls, adapter_config, environments_config, delta_store_map={}, triggers=[]):
		logger = logging.getLogger('root')
		endpoint=Endpoint(triggers, delta_store_map)
		middleware = [
			RestrictEnvironment(environments_config.sections()),
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
		try:
			for trigger in self.triggers:
				trigger(req.context['doc'], env)
		except QueuingError as e:
			self.logger.critical(e)
			raise falcon.HTTPInsufficientStorage(
				title="Queue full",
				description=("The status update could not be enqueued "
							 "because the underlying on-disk-database "
							 "has reached its maximum size"))
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
