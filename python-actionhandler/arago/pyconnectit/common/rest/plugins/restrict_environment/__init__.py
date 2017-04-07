import logging, falcon

class RestrictEnvironment(object):
	def __init__(self, environments):
		self.logger = logging.getLogger('root')
		self.environments=environments
	def process_resource(self, req, resp, resource, params):
		if 'env' in params and params['env'] not in self.environments:
			self.logger.warn("New message for unknown environment: {env}".format(env=params['env']))
			raise falcon.HTTPNotFound(
				title='Environment not defined',
				description='Environment {env} is not defined.'.format(env=params['env']))
