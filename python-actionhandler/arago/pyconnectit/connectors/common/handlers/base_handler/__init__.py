import logging

class BaseHandler(object):
	def __init__(self):
		self.logger = logging.getLogger('root')

	def __call__(self):
		raise NotImplementedError
