import traceback
import logging

class Action(object):
	def __init__(self, node, zmq_info, timeout, parameters):
		self.logger = logging.getLogger('worker')
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
		except:
			self.statusmsg="ACTIONHANDLER CRASHED!!!\n{tb}".format(
				tb=traceback.format_exc())
			self.success=False
			self.logger.critical(self.statusmsg)
		return(self)

	def __call__(self):
		self.statusmsg="ActionHandler not implemented"
