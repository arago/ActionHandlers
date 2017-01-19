import gevent

from pyactionhandler import Action
from pyactionhandler.winrm.session import krb5Session
from pyactionhandler.winrm.script import Script

import winrm.exceptions
import pyactionhandler.winrm.exceptions
import logging



class WinRMCmdAction(Action):
	def __init__(self, num, node, zmq_info, timeout, parameters, ssl=True):
		super(WinRMCmdAction, self).__init__(
			num, node, zmq_info, timeout, parameters)
		self.logger = logging.getLogger('root')
		self.customer = parameters['CustomerID'] if 'CustomerID' in parameters else 'default'
		self.ssl=ssl

	def __str__(self):
		return "cmd.exe command '{cmd}' on '{node}'".format(
			cmd=self.parameters['Command'],
			node=self.parameters['Hostname'])

	@staticmethod
	def init_direct_session(host, port, protocol):
		return krb5Session(
			endpoint="{protocol}://{hostname}:{port}/wsman".format(
				protocol=protocol,
				hostname=host,
				port=port))

	@staticmethod
	def init_script(script):
		return Script(
			script=script,
			interpreter='cmd',
			cols=120)

	def winrm_run_script(self, winrm_session):
		script=self.init_script(self.parameters['Command'])
		try:
			script.run(winrm_session)
			self.output, self.error_output = script.get_outputs()
			self.system_rc = script.rs.status_code
			self.success=True
		except (winrm.exceptions.WinRMError, winrm.exceptions.WinRMTransportError, pyactionhandler.winrm.exceptions.WinRMError) as e:
			self.statusmsg=str(e)
			self.logger.error("[{anum}] An error occured during command execution on {node}: {err}".format(anum=self.num, node=self.node,err=str(e)))

	def __call__(self):
		winrm_session=self.init_direct_session(
			host = self.parameters['Hostname'],
			protocol = 'https' if self.ssl else 'http',
			port = '5986' if self.ssl else '5985')
		self.logger.debug("[{anum}] Connecting directly to '{target}'".format(
			anum=self.num,
			target=self.parameters['Hostname']))
		self.winrm_run_script(winrm_session)

class WinRMPowershellAction(WinRMCmdAction):
	def init_script(self,script):
		return Script(
			script=script,
			interpreter='ps',
			cols=120)

	def __str__(self):
		return "powershell.exe command '{cmd}' on '{node}'".format(
			cmd=self.parameters['Command'],
			node=self.parameters['Hostname'])
