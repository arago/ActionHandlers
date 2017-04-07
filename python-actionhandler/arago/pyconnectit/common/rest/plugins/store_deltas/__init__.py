import logging

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
			except KeyError:
				self.logger.warning(
					"No DeltaStore defined for environment: {env}".format(
						env=params['env']))
