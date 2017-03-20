from arago.pyconnectit.connectors.common.handlers.base_handler import BaseHandler

class LogStatusChange(BaseHandler):
	def __call__(self, data, env):
		self.logger.verbose("Status of Event {ev} changed to {st}".format(
			ev=data['mand']['eventId'],
			st=data['free']['eventNormalizedStatus']))

	def __str__(self):
		return "LogStatusChange"
