#!/usr/bin/env python
import gevent
from gevent import monkey; monkey.patch_all()
import gevent.hub
import sys
import signal
from docopt import docopt
import logging
import logging.config
from arago.pyactionhandler.worker_collection import WorkerCollection
from arago.pyactionhandler.handler import SyncHandler
from arago.pyactionhandler.capability import Capability
from arago.common.configparser import ConfigParser
from configparser import NoSectionError, NoOptionError
from arago.common.daemon import daemon as Daemon
from arago.pyactionhandler.action import Action

############################### "Counting rhyme" example Actionhandler ###############################
#                                                                                                    #
# This ActionHandler, when called without any parameters, will return the next line from a counting  #
# rhyme and then increase its internal counter. When it reaches the end of the rhyme, it will loop.  #
#                                                                                                    #
# When called with the parameter 'Number', it will return that many lines at once.                   #
#                                                                                                    #
# If 'Number' is not a number, it will return an error message                                       #
#                                                                                                    #
######################################################################################################


class CountingRhyme(object):
	def __init__(self):
		self.lines=[
			"Eeny, meeny, miny, moe.",
			"Catch a tiger by the toe.",
			"If he hollers, let him go."
		]
		self._current = 0

	@property
	def current_line(self):
		line = self.lines[self._current]
		self._current = (self._current + 1) % len(self.lines) # increase counter, loop at the end
		return line


# This class implements the actual Actionhandler:
class CountingRhymeAction(Action):
	def __init__(self, num, node, zmq_info, timeout, parameters, rhyme):

		# Run the parent classes' contructor
		super(CountingRhymeAction, self).__init__(num, node, zmq_info, timeout, parameters)

		# Additional parameters used in the class
		self.rhyme = rhyme

	# Return a string representation of the Action object, only used for logging.
	def __str__(self):
		return "CountingRhyme action on node {node}".format(
			node=self.node)


	# This is the method that is called on each command execution
	# The Action object has a number of standard attributes that can be used during command execution:
	#
	# num:        Consecutive number of the current command for use in log messages, implemented as a generator
	# node:       NodeID of the MARS node the command is executed on
	# zmq_info:   The ZeroMQ identifier of the message, needed for the callback, DO NOT MODIFY!
	# timeout:    After that many seconds, the command execution will be automatically canceled and an error
	#             will be returned
	# parameters: Dictionary with all the parameters from the Action element in the KI
	# logger:     A python logger object
	#
	# Additional arguments can be passed to the Action object in order to manage global state like a database
	# connection or an API instance. In case of this sample ActionHandler, the same instance of the CountingRhyme
	# class is passed to each Action object.

	# In order to return the results of the operation to the HIRO engine, a number of attributes can be set.
	# They will be passed back to the calling KI automatically, so there is no need to explicitly return them.
	#
	# output:       The standard output (stdout) of the command as a (multiline) string
	# error_output: The error output (stderr) of the command
	# system_rc:    The return code of the command (int), 0 usually indicates success, any number > 0 indicates
	#               an error
	# success:      True or False, indicates if the ActionHandler itself operated as intended
	# statusmsg:    In case the ActionHandler itself failed, statusmsg should be set to a detailled message about
	#               what went wrong
	#
	def __call__(self):
		# If a 'Number' parameter is given, return this many lines of the rhyme, else return just one.
		if 'Number' in self.parameters:
			try:
				self.output = "\n".join(
					[self.rhyme.current_line for num in range(int(self.parameters['Number']))]
				)
				self.error_output = ""
				self.system_rc = 0
				self.statusmsg = ""
				self.success = True
			except ValueError: # 'Number' could not be converted to an integer
				self.output=""
				self.error_output=""
				self.success = False # this will set system_rc to -1 automatically
				self.statusmsg = "Invalid value for parameter 'Number': Not a number ;-)"
		else:
			self.output = self.rhyme.current_line
			self.error_output = ""
			self.system_rc = 0
			self.statusmsg=""
			self.success = True


# The ActionHandler is wrapped into this object in order to be properly daemonized (double fork method),
# except if it was called with --debug
#
# In this case, the loglevel is set to DEBUG automatically and logs are written to console as well as
# to the logfile.

class ActionHandlerDaemon(Daemon):
	def run(self):

		# Open config file (not actually used in this example)
		actionhandler_config=ConfigParser()
		actionhandler_config.read('/opt/autopilot/conf/external_actionhandlers/counting-rhyme-actionhandler.conf')

		# Setup logging in normal operation
		logging.config.fileConfig('/opt/autopilot/conf/external_actionhandlers/counting-rhyme-actionhandler-log.conf')
		logger = logging.getLogger('root')

		# Setup debug logging (see commandline interface at the end of the file)
		if self.debug:
			logger.setLevel(logging.DEBUG)
			ch = logging.StreamHandler()
			ch.setLevel(logging.DEBUG)
			formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s","%Y-%m-%d %H:%M:%S")
			ch.setFormatter(formatter)
			logger.addHandler(ch)
			logger.info("Logging to console and logfile")


		# An instance of the CountingRhyme class in this example demonstrates how to manage "state" that
		# is shared among all instances of the Action class.
		#
		# In a real world Actionhandler, this could be a database connection, an API etc.
		rhyme = CountingRhyme()


		# Map the "Capability" string to the Action object that implements this capability
		#
		# For each command issued by the HIRO engine, an instance will be created with a number of standard
		# parameters plus the ones you specify here
		#
		# Upon command execution, the __call__() method of the object will be called.
		capabilities = {
			"Rhyme":Capability(CountingRhymeAction, rhyme=rhyme)
		}


		# A worker collection shares the same request and response queue
		# Workers will be created as needed, one per MARS node
		# A worker will execute max. <parallel_tasks_per_worker> actions in parallel
		# A worker collection will execute max. <parallel_tasks> actions in parallel
		# Workers will be destroyed after <worker_max_idle> seconds of inactivity to free up memory
		worker_collection = WorkerCollection(
			capabilities,
			parallel_tasks = 10,
			parallel_tasks_per_worker = 3,
			worker_max_idle = 300,
		)


		# The actual ActionHandler consists of a ZeroMQ socket and a worker collection
		# It will listen for incoming messages and if it knows the capability, create an
		# Action object and put it onto the request queue of the worker collection.
		#
		# The worker collection will then lookup if there's already a Worker for the MARS
		# node the command originated from or create a new one. It will then remove the Action
		# object from the worker collection's request queue and put it onto the worker's queue
		#
		# The Worker will remove the first <parallel_tasks_per_worker> action(s) from its queue,
		# execute them and put the results back onto the worker collection's response queue.
		try:
			if not actionhandler_config.getboolean('Encryption', 'enabled'):
				raise ValueError
			zmq_auth = (
				actionhandler_config.get('Encryption', 'server-public-key', raw=True).encode('ascii'),
				actionhandler_config.get('Encryption', 'server-private-key', raw=True).encode('ascii')
			)
		except (ValueError, NoSectionError, NoOptionError):
			zmq_auth = None

		counting_rhyme_handler = SyncHandler(
			worker_collection,
			# The socket(s) the Actionhandler will listen on, hardcoded in this example but
			# should really be read from a config file
			zmq_url = 'tcp://*:7291',
			auth = zmq_auth
		)


		action_handlers = [counting_rhyme_handler] # list of all defined Actionhandlers


		# Function to shutdown gracefully by letting all current commands finish
		def exit_gracefully():
			logger.info("Starting shutdown")
			for action_handler in action_handlers:
				action_handler.shutdown()
				logger.info("Finished shutdown")

		# Graceful shutdown can be triggered by SIGINT and SIGTERM
		gevent.hub.signal(signal.SIGINT, exit_gracefully)
		gevent.hub.signal(signal.SIGTERM, exit_gracefully)


		# Start main gevent loop
		greenlets=[action_handler.run() for action_handler in action_handlers]
		gevent.idle() # Pass control over the event loop to the other greenlets, so they can initialize
		gevent.joinall(greenlets) # waits until all greenlet pseudo-threads terminate
		sys.exit(0)


# Command line interface
if __name__ == "__main__":
	usage="""Usage:
  {progname} [options] (start|stop|restart)

Options:
  --debug            do not run as daemon and log to stderr
  --pidfile=PIDFILE  Specify pid file [default: /var/run/{progname}.pid]
  -h --help          Show this help screen
""".format(progname='autopilot-counting-rhyme-actionhandler')

	args=docopt(usage) # see http://docopt.org

	daemon = ActionHandlerDaemon(args['--pidfile'], debug=args['--debug'])

	if args['start']: daemon.start()
	elif args['stop']: daemon.stop()
	elif args['restart']: daemon.restart()

	sys.exit(0)
