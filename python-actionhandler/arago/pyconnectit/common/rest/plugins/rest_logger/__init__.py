import logging
from arago.common.helper import prettify

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
