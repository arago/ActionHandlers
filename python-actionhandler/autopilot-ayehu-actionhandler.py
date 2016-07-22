#!/usr/bin/env python
import gevent
from gevent import pywsgi
from gevent import monkey; monkey.patch_all()
import zeep
import redis
import redis.connection
import falcon
import sys
import gevent.hub
import signal
import time
from docopt import docopt
import logging
import logging.config
from configparser import ConfigParser
from pyactionhandler import WorkerCollection, SyncHandler
from pyactionhandler.ayehu import AyehuAction, AyehuBackgroundAction
from pyactionhandler.ayehu.zeep_redis_cache import RedisCache
import pyactionhandler.ayehu.REST as rest
from pyactionhandler.daemon import daemon

class ActionHandlerDaemon(daemon):
	def run(self):
		logging.config.fileConfig('/opt/autopilot/conf/pyactionhandler_log.conf')
		logger = logging.getLogger('root')

		redis.connection.socket = gevent.socket

		ayehu_config = ConfigParser()
		ayehu_config.read('/opt/autopilot/conf/ayehu.conf')

		pmp_config = ConfigParser()
		pmp_config.read('/opt/autopilot/conf/pmp.conf')

		# Redis datastore for commands handed to Ayehu
		commands_redis = redis.StrictRedis(
			host=ayehu_config.get('default', 'CommandsRedisHost'),
			port=ayehu_config.get('default', 'CommandsRedisPort'),
			db=ayehu_config.get('default', 'CommandsRedisDB'),
			charset = "utf-8",
			decode_responses = True)
		commands_pubsub = commands_redis.pubsub(ignore_subscribe_messages=True)

		# Redis datastore for zeep's cache
		zeep_cache_redis = redis.StrictRedis(
			host=ayehu_config.get('default', 'ZeepCacheRedisHost'),
			port=ayehu_config.get('default', 'ZeepCacheRedisPort'),
			db=ayehu_config.get('default', 'ZeepCacheRedisDB'))
		zeep_cache = RedisCache(timeout=3600, redis=zeep_cache_redis)
		zeep_transport = zeep.transports.Transport(cache=zeep_cache)
		zeep_client = zeep.Client(
			ayehu_config.get('default', 'URL'),transport=zeep_transport)

		# Setup REST API for callback
		rest_api = rest.RESTAPI(
			baseurl=ayehu_config.get('default', 'CallbackBaseURL'),
			redis=commands_redis,
			pubsub=commands_pubsub)

		server = pywsgi.WSGIServer(
			('', 8080), rest_api.app)

		action_handlers = [SyncHandler(
			WorkerCollection(
				{"ExecuteWorkflow":(AyehuAction, {
					'zeep_client':zeep_client,
					'redis':commands_redis,
					'ayehu_config':ayehu_config,
					'pmp_config':pmp_config,
					'rest_api':rest_api}),
				 "ExecuteWorkflowInBackground":(AyehuBackgroundAction, {})},
				parallel_tasks=5,
				parallel_tasks_per_worker=5,
				worker_max_idle=300),
			zmq_url="tcp://127.0.0.1:7289")]


		def exit_gracefully():
			logger.info("Starting shutdown")
			for action_handler in action_handlers:
				action_handler.shutdown()
				logger.info("Finished shutdown")
			server.stop()


		gevent.hub.signal(signal.SIGINT, exit_gracefully)
		gevent.hub.signal(signal.SIGTERM, exit_gracefully)
		# ActionHandlers:
		greenlets=[action_handler.run() for action_handler in action_handlers]
		gevent.idle()
		server.serve_forever()
		gevent.joinall(greenlets)
		sys.exit()

if __name__ == "__main__":
	usage="""Usage:
  {progname} [options] (start|stop|restart)

Options:
  --pidfile=PIDFILE  Specify pid file [default: /var/run/{progname}.pid]
  -h --help          Show this help screen
""".format(progname='autopilot-ayehu-actionhandler')

	args=docopt(usage)
	daemon = ActionHandlerDaemon(args['--pidfile'])
	if args['start']:
		daemon.start()
	elif args['stop']:
		daemon.stop()
	elif args['restart']:
		daemon.restart()
	sys.exit(0)
