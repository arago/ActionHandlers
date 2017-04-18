import gevent
import gevent.subprocess

from arago.pyactionhandler.action import Action
from arago.pyactionhandler.plugins.winrm.auth.kerberos import krb5Session
from arago.pyactionhandler.plugins.winrm.script import Script

import winrm.exceptions
import arago.pyactionhandler.plugins.winrm.exceptions
import logging
import re

from requests_kerberos.exceptions import KerberosExchangeError



class WinRMCmdAction(Action):
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

	def parse_krb5_err(self, err):
		result = re.search(r"authGSSClientStep\(\) failed: \(\((?P<q1>'|\")(?P<major_desc>.+)(?P=q1), (?P<major_code>-?[\d]+)\), \((?P<q2>'|\")(?P<minor_desc>.+)(?P=q2), (?P<minor_code>-?[\d]+)\)\)", err)
		return result.group('minor_desc') if result else None

	def winrm_run_script(self, winrm_session):
		script=self.init_script(self.parameters['Command'])
		for i in range(3):
			try:
				script.run(winrm_session)
				self.output, self.error_output = script.get_outputs()
				self.system_rc = script.rs.status_code
				self.success=True
			except KerberosExchangeError as e:
				parsed_err = self.parse_krb5_err(str(e))
				self.statusmsg=str(e)
				self.success=False
				self.system_rc=-1
				if parsed_err == "Ticket expired" or (parsed_err.startswith("Credentials cache file ") and parsed_err.endswith(" not found")):
					self.logger.warning("[{anum}] No Kerberos ticket for {host}, requesting one ...".format(anum=self.num, host=self.parameters['Hostname']))
					try:
						gevent.subprocess.check_output(["kinit", "-k", "-t", self.parameters['Keytab'], self.parameters['Username']], timeout=30, stderr=gevent.subprocess.STDOUT)
						self.logger.info("[{anum}] Successfully retrieved Kerberos ticket for {host}, retrying command execution.".format(anum=self.num, host=self.parameters['Hostname']))
					except gevent.subprocess.CalledProcessError as e:
						self.logger.error("[{anum}] Retrieving Kerberos ticket for {host} failed: {err}".format(anum=self.num, host=self.parameters['Hostname'], err=e.output.decode("utf-8")))
					except gevent.subprocess.TimeoutExpired as e:
						self.logger.error("[{anum}] Retrieving Kerberos ticket for {host} timed out!".format(anum=self.num, host=self.parameters['Hostname']))
					except KeyError:
						self.logger.error("[{anum}] Retrieving Kerberos ticket for {host} failed! Credentials missing!".format(anum=self.num, host=self.parameters['Hostname']))
					continue
				else:
					self.logger.error("[{anum}] An error occured during command execution on {node}: Kerberos: {err}".format(anum=self.num, node=self.node,err=parsed_err))
			except (winrm.exceptions.WinRMError, winrm.exceptions.WinRMTransportError, arago.pyactionhandler.plugins.winrm.exceptions.WinRMError, requests.exceptions.ConnectTimeout) as e:
				self.statusmsg=str(e)
				self.success=False
				self.system_rc=-1
				self.logger.error("[{anum}] An error occured during command execution on {node}: {err}".format(anum=self.num, node=self.node,err=str(e)))
			break

	def __call__(self):
		winrm_session=self.init_direct_session(
			host = self.parameters['Hostname'],
			protocol = 'https' if self.parameters['UseSSL'] == 'true' else 'http',
			port = '5986' if self.parameters['UseSSL'] == 'true' else '5985')
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
