import winrm
import base64
import urllib.parse as urlparse

import arago.pyactionhandler.plugins.winrm.exceptions
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
				raise arago.pyactionhandler.plugins.winrm.exceptions.WinRMError(
					"No Connection to jumpserver on {jump}: {reason}".format(jump=urlparse.urlparse(self.protocol.transport.endpoint).netloc, reason=e))
		else:
			exe = "mode con: cols=1052 & powershell -NoProfile -encodedcommand %s" % (base64_script)
			rs = self.run_cmd(exe)
		if rs.std_err:
			raise arago.pyactionhandler.plugins.winrm.exceptions.WinRMError(rs.std_err.decode('cp850'))
		return rs
