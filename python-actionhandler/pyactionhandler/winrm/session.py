import winrm
import base64
import urllib.parse as urlparse

import pyactionhandler.winrm.exceptions
import requests.exceptions

class Session(winrm.Session):

	def run_ps(self, script):
		"""base64 encodes a Powershell script and executes the powershell encoded script command"""

		# must use utf16 little endian on windows
		base64_script = base64.b64encode(script.encode("utf_16_le")).decode('cp850')
		if self.target:
			username, password = self.target_auth
			exe = "mode con: cols=1052 & powershell -Command \"$username='{usr}';$password=ConvertTo-SecureString '{pw}' -AsPlainText -Force;$cred = new-object -typename System.Management.Automation.PSCredential -argumentlist $username,$password;invoke-command -computername {target} -authentication Negotiate -credential $cred -scriptblock {{powershell -encodedcommand {script}}}\"".format(target=self.target, script=base64_script, usr=username, pw=password)
			try:
				rs = self.run_cmd(exe)
			except requests.exceptions.ConnectionError as e:
				raise pyactionhandler.winrm.exceptions.WinRMError(
					"No Connection to jumpserver on {jump}: {reason}".format(jump=urlparse.urlparse(self.protocol.transport.endpoint).netloc, reason=e))
		else:
			exe = "mode con: cols=1052 & powershell -encodedcommand %s" % (base64_script)
			rs = self.run_cmd(exe)
		if rs.std_err:
			raise pyactionhandler.winrm.exceptions.WinRMError(rs.std_err.decode('cp850'))
		return rs

class certSession(Session):
	def __init__(self, endpoint, certificate, target=None, target_auth=None, validation='ignore'):
		self.protocol = winrm.Protocol(
			endpoint=endpoint,
			transport='certificate',
			server_cert_validation=validation,
			cert_pem=certificate,
			cert_key_pem=certificate
		)
		if target and target_auth:
			self.target = target
			self.target_auth = (target_auth.WindowsUserName, target_auth.passwd())
		else:
			self.target=None
			self.target_auth=None

class basicSession(Session):
	def __init__(self, endpoint, auth, target=None, target_auth=None, transport='ssl', validation='ignore'):
		username, password = auth
		self.protocol = winrm.Protocol(
			endpoint=endpoint,
			transport=transport,
			username=username,
			password=password,
			server_cert_validation=validation
		)
		self.target = target
		self.target_auth = target_auth

class PMPSession(Session):
	def __init__(self, endpoint, auth, target=None, target_auth=None, transport='ssl', validation='ignore'):
		username = auth.AccountName
		password = auth.passwd()
		self.protocol = winrm.Protocol(
			endpoint=endpoint,
			transport=transport,
			username=username,
			password=password,
			server_cert_validation=validation
		)
		self.target = target
		self.target_auth = (target_auth.WindowsUserName, target_auth.passwd())

class krb5Session(Session):
	def __init__(self, endpoint, auth, target=None, validation='ignore'):
		self.protocol = winrm.Protocol(
			endpoint=endpoint,
			transport='kerberos',
			server_cert_validation=validation,
			kerberos_delegation=True
		)
		self.target = target
