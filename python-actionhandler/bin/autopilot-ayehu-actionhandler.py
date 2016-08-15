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
from pyactionhandler import WorkerCollection, SyncHandler, Capability, ConfigParser, Daemon
from pyactionhandler.ayehu import AyehuAction, AyehuBackgroundAction, RESTAPI, RedisCache

class ActionHandlerDaemon(Daemon):
	def run(self):

		actionhandler_config=ConfigParser()
		actionhandler_config.read('/opt/autopilot/conf/pyactionhandler/ayehu-actionhandler.conf')

		logging.config.fileConfig('/opt/autopilot/conf/pyactionhandler/ayehu-actionhandler-log.conf')
		logger = logging.getLogger('root')
		if self.debug:
			logger.setLevel(logging.DEBUG)
			ch = logging.StreamHandler()
			ch.setLevel(logging.DEBUG)
			formatter = logging.Formatter(
				"%(asctime)s [%(levelname)s] %(message)s","%Y-%m-%d %H:%M:%S")
			ch.setFormatter(formatter)
			logger.addHandler(ch)
			logger.info("Logging also to console")

		redis.connection.socket = gevent.socket

		ayehu_config = ConfigParser()
		ayehu_config.read('/opt/autopilot/conf/pyactionhandler/ayehu-actionhandler-ayehu.conf')

		pmp_config = ConfigParser()
		pmp_config.read('/opt/autopilot/conf/pyactionhandler/pmp.conf')

		# Redis datastore for commands handed to Ayehu
		commands_redis = redis.StrictRedis(
			host=actionhandler_config.get('RESTInterface', 'RedisHost'),
			port=actionhandler_config.get('RESTInterface', 'RedisPort'),
			db=actionhandler_config.get('RESTInterface', 'RedisDB'),
			charset = "utf-8",
			decode_responses = True)
		commands_pubsub = commands_redis.pubsub(ignore_subscribe_messages=True)

		# Redis datastore for zeep's cache
		zeep_cache_redis = redis.StrictRedis(
			host=actionhandler_config.get('SOAPClient', 'RedisHost'),
			port=actionhandler_config.get('SOAPClient', 'RedisPort'),
			db=actionhandler_config.get('SOAPClient', 'RedisDB'))
		zeep_cache = RedisCache(timeout=3600, redis=zeep_cache_redis)
		zeep_transport = zeep.transports.Transport(cache=zeep_cache)

		# Setup REST API for callback
		rest_api = RESTAPI(
			baseurl=actionhandler_config.get('RESTInterface', 'CallbackBaseURL'),
			redis=commands_redis,
			pubsub=commands_pubsub)

		server = pywsgi.WSGIServer(
			('', 8080), rest_api.app, log=None, error_log=None)

		action_handlers = [SyncHandler(
			WorkerCollection(
				{"ExecuteWorkflow":Capability(AyehuAction,
					zeep_transport=zeep_transport,
					redis=commands_redis,
					ayehu_config=ayehu_config,
					pmp_config=pmp_config,
					rest_api=rest_api)},
				parallel_tasks = actionhandler_config.getint(
					'ActionHandler', 'ParallelTasks', fallback=10),
				parallel_tasks_per_worker = actionhandler_config.getint(
					'ActionHandler', 'ParallelTasksPerWorker', fallback=10),
				worker_max_idle = actionhandler_config.getint('ActionHandler', 'WorkerMaxIdle', fallback=300)),
			zmq_url = actionhandler_config.get('ActionHandler', 'ZMQ_URL'))]

		def exit_gracefully():
			logger.info("Starting shutdown")
			for action_handler in action_handlers:
				action_handler.shutdown()
				logger.info("Finished shutdown")
			server.stop()


		gevent.hub.signal(signal.SIGINT, exit_gracefully)
		gevent.hub.signal(signal.SIGTERM, exit_gracefully)
		greenlets=[action_handler.run() for action_handler in action_handlers]
		gevent.idle()
		server.serve_forever()
		gevent.joinall(greenlets)
		sys.exit()

if __name__ == "__main__":
	usage="""Usage:
  {progname} [options] (start|stop|restart)

Options:
  --debug            do not run as daemon and log to stderr
  --pidfile=PIDFILE  Specify pid file [default: /var/run/{progname}.pid]
  -h --help          Show this help screen
""".format(progname='autopilot-ayehu-actionhandler')

	args=docopt(usage)
	daemon = ActionHandlerDaemon(args['--pidfile'], debug=args['--debug'])
	if args['start']: daemon.start()
	elif args['stop']: daemon.stop()
	elif args['restart']: daemon.restart()
	sys.exit(0)
