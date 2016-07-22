#!/usr/bin/env python
import gevent
from gevent import pywsgi
from gevent import monkey; monkey.patch_all()
import sys
import gevent.hub
import signal
import time
from docopt import docopt
import logging
import logging.config
from pyactionhandler.configparser import FallbackConfigParser as ConfigParser
from pyactionhandler import WorkerCollection, SyncHandler
from pyactionhandler.winrm import WinRMCmdAction, WinRMPowershellAction
from pyactionhandler.daemon import daemon

class ActionHandlerDaemon(daemon):
	def run(self):

		actionhandler_config=ConfigParser()
		actionhandler_config.read('/opt/autopilot/conf/pyactionhandler/winrm-actionhandler.conf')

		logging.config.fileConfig('/opt/autopilot/conf/pyactionhandler/winrm-actionhandler-log.conf')
		logger = logging.getLogger('root')

		# Read config files
		jumpserver_config = ConfigParser()
		jumpserver_config.read('/opt/autopilot/conf/pyactionhandler/winrm-actionhandler-jumpserver.conf')

		pmp_config = ConfigParser()
		pmp_config.read('/opt/autopilot/conf/pyactionhandler/pmp.conf')

		action_handlers = [SyncHandler(
			WorkerCollection(
				{"ExecuteCommand":(WinRMCmdAction, {
					 'pmp_config':pmp_config,
					 'jumpserver_config':jumpserver_config}),
				 "ExecutePowershell":(WinRMPowershellAction, {
					 'pmp_config':pmp_config,
					 'jumpserver_config':jumpserver_config})},
				parallel_tasks = actionhandler_config.getint(
					'default', 'ParallelTasks', fallback=5),
				parallel_tasks_per_worker = actionhandler_config.getint(
					'default', 'ParallelTasksPerWorker', fallback=5),
				worker_max_idle = actionhandler_config.getint('default', 'WorkerMaxIdle', fallback=300)),
			zmq_url = actionhandler_config.get('default', 'ZMQ_URL'))]

		def exit_gracefully():
			logger.info("Starting shutdown")
			for action_handler in action_handlers:
				action_handler.shutdown()
				logger.info("Finished shutdown")

		gevent.hub.signal(signal.SIGINT, exit_gracefully)
		gevent.hub.signal(signal.SIGTERM, exit_gracefully)
		# ActionHandlers:
		greenlets=[action_handler.run() for action_handler in action_handlers]
		gevent.idle()
		gevent.joinall(greenlets)
		sys.exit()

if __name__ == "__main__":
	usage="""Usage:
  {progname} [options] (start|stop|restart)

Options:
  --pidfile=PIDFILE  Specify pid file [default: /var/run/{progname}.pid]
  -h --help          Show this help screen
""".format(progname='autopilot-winrm-actionhandler')

	args=docopt(usage)
	daemon = ActionHandlerDaemon(args['--pidfile'])
	if args['start']:
		daemon.start()
	elif args['stop']:
		daemon.stop()
	elif args['restart']:
		daemon.restart()
	sys.exit(0)
