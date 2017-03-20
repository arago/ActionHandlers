import datetime
from arago.pyconnectit.connectors.common.handlers.base_handler import BaseHandler

class LogComments(BaseHandler):
	def __call__(self, data, env):
		for comment in sorted(
				data['opt']['comment'],
				key=lambda comment: comment['opt']['timestamp']):
			self.logger.verbose((
				"A comment was added to event {ev}"
				" at {time}: {comment}").format(
					ev=data['mand']['eventId'],
					time=datetime.datetime.fromtimestamp(
						int(comment['opt']['timestamp'])/1000).strftime(
							'%Y-%m-%d %H:%M:%S'),
					comment=comment['opt']['content']))

	def __str__(self):
		return "LogComments"
