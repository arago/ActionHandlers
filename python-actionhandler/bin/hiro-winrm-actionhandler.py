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
from arago.pyactionhandler.worker_collection import WorkerCollection
from arago.pyactionhandler.handler import SyncHandler
from arago.pyactionhandler.capability import Capability
from arago.common.configparser import ConfigParser
from arago.common.daemon import daemon as Daemon
from arago.pyactionhandler.plugins.winrm import WinRMCmdAction, WinRMPowershellAction

class ActionHandlerDaemon(Daemon):
	def run(self):

		actionhandler_config=ConfigParser()
		actionhandler_config.read((
			'/opt/autopilot/conf/external_actionhandlers/'
			'winrm-actionhandler.conf'))

		logging.config.fileConfig((
			'/opt/autopilot/conf/external_actionhandlers/'
			'winrm-actionhandler-log.conf'))
		logger = logging.getLogger('root')
		if self.debug:
			logger.setLevel(logging.DEBUG)
			ch = logging.StreamHandler()
			ch.setLevel(logging.DEBUG)
			formatter = logging.Formatter(
				"%(asctime)s [%(levelname)s] %(message)s",
				"%Y-%m-%d %H:%M:%S")
			ch.setFormatter(formatter)
			logger.addHandler(ch)
			logger.info("Logging also to console")

		action_handlers = [SyncHandler(
			WorkerCollection(
				{"ExecuteCommand":Capability(WinRMCmdAction, ssl=False),
				 "ExecutePowershell":Capability(WinRMPowershellAction, ssl=False)},
				parallel_tasks = actionhandler_config.getint(
					'ActionHandler', 'ParallelTasks', fallback=5),
				parallel_tasks_per_worker = actionhandler_config.getint(
					'ActionHandler', 'ParallelTasksPerWorker', fallback=5),
				worker_max_idle = actionhandler_config.getint(
					'ActionHandler', 'WorkerMaxIdle', fallback=300)),
			zmq_url = actionhandler_config.get(
				'ActionHandler', 'ZMQ_URL'))]

		def exit_gracefully():
			logger.info("Starting shutdown")
			for action_handler in action_handlers:
				action_handler.shutdown()
				logger.info("Finished shutdown")

		gevent.hub.signal(signal.SIGINT, exit_gracefully)
		gevent.hub.signal(signal.SIGTERM, exit_gracefully)
		greenlets=[action_handler.run() for action_handler in action_handlers]
		gevent.idle()
		gevent.joinall(greenlets)
		sys.exit()

if __name__ == "__main__":
	usage="""Usage:
  {progname} [options] (start|stop|restart)

Options:
  --debug            do not run as daemon and log to stderr
  --pidfile=PIDFILE  Specify pid file [default: /var/run/{progname}.pid]
  -h --help          Show this help screen
""".format(progname='autopilot-winrm-actionhandler')

	args=docopt(usage)
	daemon = ActionHandlerDaemon(args['--pidfile'], debug=args['--debug'])
	if   args['start']: daemon.start()
	elif args['stop']: daemon.stop()
	elif args['restart']: daemon.restart()
	sys.exit(0)
