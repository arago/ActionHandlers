import logging
from arago.pyconnectit.common.delta_store import DeltaStoreFull
import falcon

class StoreDeltas(object):
	def __init__(self, resources, delta_store_map):
		self.logger = logging.getLogger('root')
		self.resources = resources
		self.delta_store_map = delta_store_map
	def process_resource(self, req, resp, resource, params):
		if 'doc' in req.context and resource in self.resources:
			try:
				self.logger.debug("Storing delta in {store}".format(
					store=self.delta_store_map[params['env']]))
				self.delta_store_map[params['env']].append(
					req.context['doc']['mand']['eventId'],
					req.context['doc']
				)
			except DeltaStoreFull as e:
				self.logger.critical("DeltaStore for {env} can't store this delta: {err}".format(env=params['env'], err=e))
				raise falcon.HTTPInsufficientStorage(title="DeltaStore full", description="")
			except KeyError:
				self.logger.warning(
					"No DeltaStore defined for environment: {env}".format(
						env=params['env']))
