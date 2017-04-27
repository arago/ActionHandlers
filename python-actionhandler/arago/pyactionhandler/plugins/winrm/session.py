import winrm
import base64
import urllib.parse as urlparse

import arago.pyactionhandler.plugins.winrm.exceptions
import requests.exceptions

class Session(winrm.Session):

	def run_ps(self, script):
		"""base64 encodes a Powershell script and executes the powershell encoded script command"""

		# must use utf16 little endian on windows
		script_bytes = script.encode('utf-8')
		packed_expression = base64.b64encode(script_bytes).decode('cp850')
		expression_template = (
 			'Invoke-Expression '
 			'$([System.Text.Encoding]::UTF8.GetString('
 				"[Convert]::FromBase64String('{0}'))"  # NOQA
 				')'
 			)
		command = expression_template.format(packed_expression)
		exe = 'mode con: cols=1052 & powershell -NoProfile -command "{0}"'.format(command)
		rs = self.run_cmd(exe)
		if rs.std_err:
			raise arago.pyactionhandler.plugins.winrm.exceptions.WinRMError(rs.std_err.decode('cp850'))
		return rs
