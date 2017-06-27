import gevent
import logging, time
from arago.pyconnectit.common.lmdb_queue import Empty, Full
from arago.pyconnectit.connectors.netcool.handlers.sync_netcool_status import StatusUpdate

class NoIssueWatcher(object):
	def __init__(self, watchlist, queue, env, interval=60, max_age=300):
		self.logger = logging.getLogger('root')
		self.watchlist=watchlist
		self.queue=queue
		self.env=env
		self.interval=interval
		self.max_age=max_age
		self.loop=gevent.Greenlet(self.sync)

	def start(self):
		self.loop.start()

	def halt(self):
		self.loop.kill()

	def serve_forever(self):
		self.loop.start()
		self.loop.join()

	def sync(self):
		self.logger.info("Started watching new events "
						 "for {env}, interval is {sleep} seconds, timeout is {to} seconds".format(
							 env=self.env,
							 sleep=self.interval,
							 to=self.max_age))
		gevent.sleep(self.interval)
		while True:
			try:
				stale_events = self.watchlist.get_untouched(self.max_age)
				for event in stale_events:
					event_id = event['mand']['eventId']
					self.logger.verbose("Event {ev} found to be stale".format(ev=event_id))
					event['free']['eventNormalizedStatus'] = [{'value':'No_issue_created', 'timestamp':str(int(time.time() * 1000))}]
					status_update = StatusUpdate(event_id, event)
					self.queue.put(status_update)
					self.watchlist.delete(event_id)
			except Full:
				raise QueuingError("Queue full")
			except KeyError as e:
				self.logger.warn("No queue defined for {env}".format(
					env=self.env))
			finally:
				gevent.sleep(self.interval)
