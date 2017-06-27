from arago.pyconnectit.connectors.common.handlers.base_handler import BaseHandler

class Watch(BaseHandler):
	def __init__(self, watchlist_map):
		super().__init__()
		self.watchlist_map=watchlist_map

	def __call__(self, data, env):
		try:
			self.watchlist_map[env].append(data['mand']['eventId'], data)
			self.logger.verbose("Starting to watch new Event {ev}".format(
				ev=data['mand']['eventId']))
		except DeltaStoreFull as e:
			self.logger.critical("Watchlist for {env} can't store this event: {err}".format(env=env, err=e))
		except KeyError:
			self.logger.warning(
				"No Watchlist defined for environment: {env}".format(
					env=env))

	def __str__(self):
		return "Watch"


class Unwatch(BaseHandler):
	def __init__(self, watchlist_map):
		super().__init__()
		self.watchlist_map=watchlist_map

	def __call__(self, data, env):
		try:
			self.watchlist_map[env].delete(data['mand']['eventId'])
			self.logger.verbose("Stopping to watch Event {ev}".format(
				ev=data['mand']['eventId']))
		except DeltaStoreFull as e:
			self.logger.critical("Watchlist for {env} can't delete this event: {err}".format(env=env, err=e))
		except KeyError:
			self.logger.warning(
				"No Watchlist defined for environment: {env}".format(
					env=env))

	def __str__(self):
		return "Unwatch"
