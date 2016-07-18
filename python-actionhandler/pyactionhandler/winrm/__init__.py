import gevent

from pyactionhandler import Action
from pyactionhandler.winrm.session import certSession
from pyactionhandler.winrm.script import Script

from pyactionhandler.common.pmp import PMPSession, TokenAuth, PMPCredentials

from winrm.exceptions import WinRMError, WinRMTransportError

class WinRMCmdAction(Action):
	def __init__(self, node, zmq_info, timeout, parameters, pmp_config,
				 ssl=True):
		super(WinRMCmdAction, self).__init__(
			node, zmq_info, timeout, parameters)
		self.pmp_config=pmp_config
		self.ssl=ssl

	def init_direct_session(self, host, port, protocol, auth):
		return certSession(
			endpoint="{protocol}://{hostname}:{port}/wsman".format(
				protocol=protocol,
				hostname=host,
				port=port),
			auth=auth)

	def init_jump_session(self, jump_host, jump_port, jump_protocol,
						  jump_auth, target_host, target_auth):
		return certSession(
			endpoint="{protocol}://{hostname}:{port}/wsman".format(
				protocol = jump_protocol,
				hostname = jump_host,
				port=jump_port),
			auth=jump_auth,
			target=target_host,
			target_auth=target_auth)

	def init_pmp_session(self, pmp_endpoint, pmp_token):
		return PMPSession(
			pmp_endpoint,
			auth=TokenAuth(pmp_token),
			verify=False)

	def init_script(self,script):
		return Script(
			script=script,
			interpreter='cmd',
			cols=120)

	def pmp_get_credentials(self, pmp_session, resource, account):
		return PMPCredentials(
			pmp_session, ResourceName=resource, AccountName=account)

	def __call__(self):

		pmp_session=self.init_pmp_session(
			pmp_endpoint=self.pmp_config('URL'),
			pmp_token=self.pmp_config('Token'))
		target_auth=self.pmp_get_credentials(
			pmp_session=pmp_session,
			resource=self.parameters['Hostname'],
			account=self.parameters['ServiceAccount'])

		if 'RemoteExecutionServer' in parameters:
			jump_auth=self.pmp_get_credentials(
				pmp_session=pmp_session,
				resource=self.parameters['RemoteExecutionServer'],
				account='keine Ahnung!!!')
			winrm_session=self.init_jump_session(
				jump_host=self.parameters['RemoteExecutionServer'],
				jump_protocol = 'https' if self.ssl else 'http',
				jump_port = '5986' if self.ssl else '5985',
				jump_auth = jump_auth,
				target_host=self.parameters['Hostname'],
				target_auth=target_auth)
		else:
			winrm_session=self.init_direct_session(
				host = self.parameters['Hostname'],
				protocol = 'https' if self.ssl else 'http',
				port = '5986' if self.ssl else 'http',
				auth=target_auth)
		script=self.init_script(self.parameters['Command'])
		try:
			script.run(winrm_session)
			self.output, self.error_output = script.get_outputs()
			self.systemrc = script.rs.status_code
			self.success=True
		except (WinRMError, WinRMTransportError) as e:
			self.statusmsg=str(e)

class WinRMPowershellAction(WinRMCmdAction):
	pass
