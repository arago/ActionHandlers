from arago.pyactionhandler.plugins.winrm.session import Session
import winrm

class krb5Session(Session):
	def __init__(self, endpoint, target=None, validation='ignore'):
		self.protocol = winrm.Protocol(
			endpoint=endpoint,
			transport='kerberos',
			server_cert_validation=validation,
			kerberos_delegation=True
		)
		self.target = target
