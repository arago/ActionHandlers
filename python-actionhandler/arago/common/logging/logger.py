import logging

class Logger(logging.getLoggerClass()):
	CRITICAL=50
	ERROR=40
	WARNING=30
	INFO=20
	VERBOSE=15
	DEBUG=10
	TRACE= 5
	NOTSET=0
	def __init__(self, name, level=logging.NOTSET):
		super().__init__(name, level)
		logging.addLevelName(self.VERBOSE, "VERBOSE")
		logging.addLevelName(self.TRACE, "TRACE")
	def verbose(self, msg, *args, **kwargs):
		if self.isEnabledFor(self.VERBOSE):
			self._log(self.VERBOSE, msg, args, **kwargs)
	def trace(self, msg, *args, **kwargs):
		if self.isEnabledFor(self.TRACE):
			self._log(self.TRACE, msg, args, **kwargs)
