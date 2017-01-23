import traceback
import logging

class Action(object):
	def __init__(self, num, node, zmq_info, timeout, parameters):
		self.logger = logging.getLogger('root')
		self.num=num
		self.node=node
		self.zmq_info=zmq_info
		self.parameters=parameters
		self.timeout=timeout
		self.output=""
		self.error_output=""
		self.system_rc=-1
		self.statusmsg=""
		self.success=False

	def __execute__(self):
		try:
			self()
		except Exception as e:
			self.logger.debug(e)
			self.statusmsg="ACTIONHANDLER CRASHED DURING ACTION"
			self.statusmsg += "\n" + traceback.format_exc()
			self.success=False
			self.logger.critical(self.statusmsg)
		return(self)

	def __call__(self):
		self.statusmsg="ActionHandler not implemented"

class FailedAction(Action):
	def __call__(self):
		self.statusmsg = "COULD NOT INITIALIZE ACTION"
		self.success = False

	def __str__(self):
		return "a failed command in order to return the error message to the KI."
