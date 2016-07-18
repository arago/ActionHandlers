import gevent

from pyactionhandler import Action
from pyactionhandler.winrm import certSession, Script
from pyactionhandler.common.pmp import PMPSession, TokenAuth, PMPCredentials

from winrm import WinRMError, WinRMTransportError

class WinRMCmdAction(Action):
	def __init__(self, node, zmq_info, timeout, parameters):
		super(WinRMCmdAction, self).__init__(
			node, zmq_info, timeout, parameters)
		pmp_session=PMPSession("pmpurl")
		pmp_session.auth=TokenAuth("pmptoken")
		pmp_session.verify=False
		target_auth=PMPCredentials(
			pmp_session,
			ResourceName=,
			AccountName=)
		self.winrm_session=certSession(
			endpoint="jumpserver_winrm_url",
			auth=("path/to/certificate", "path/to/keyfile"),
			target="targetserver_winrm_hostname",
			target_auth=target_auth)
		self.script=Script(
			script="commands as utf8",
			interpreter='cmd',
			cols=120)

	def init_direct_session(self, host, port, protocol, auth):
		pass

	def init_jump_session(
			self, jump_host, jump_port, jump_protocol, jump_auth,
			target_host, target_port, target_protocol, target_auth):
		pass

	def pmp_get_credentials(self):
		pass

	def pmp_get_certificate(self):
		pass

	def __call__(self):
		try:
			self.script.run(winrm_session)
			self.output, self.error_output=script.print_output()
			self.systemrc = script.rs.status_code
		except (WinRMError, WinRMTransportError) as e:
			self.statusmsg=str(e)
