from pyactionhandler.common.pmp.exceptions import PMPError
from functools import reduce
import winrm
import base64
import uuid as uuid_mod

class Wrapper(object):

	@staticmethod
	def bash_quote(string):
		return '"%s"' % (
			string
			.replace('\\', '\\\\')
			.replace('"', '\\"')
			.replace('$', '\\$')
			.replace('`', '\\`')
		)

	@staticmethod
	def powershell_quote(string):
		return '"%s"' % (
			string
			.replace('`', '``')
			.replace('"', '`"')
			.replace('$', '`$')
		)

	def get_wrapper(self, initiator, target):
		decision_matrix = {
			('windows', 'windows', 'winrm'): self.cmd_win_win_winrm,
			('unix', 'windows', 'winrm'): self.cmd_unix_win_winrm,
			('windows', 'unix', 'ssh'): self.cmd_win_unix_ssh,
			('unix', 'unix', 'ssh'): self.cmd_unix_unix_ssh
		}
		try:
			return decision_matrix[(initiator.system,
									target.system,
									target.protocol)]
		except KeyError:
			raise WrapperError("No Wrapper for connecting from {initsys} to {targetsys} via {proto}".format(initsys=initiator.system, targetsys=target.system, proto=target.protocol))

	def wrap(self, route, target, command):
		def helper(target, initiator):
			wrapper = self.get_wrapper(initiator, target)
			initiator.cmd = wrapper(target.cmd, initiator, target)
			return initiator
		target.cmd=command
		return reduce(helper, reversed(route.hops + [target]))

	def cmd_win_win_winrm(self, command, initiator, target):
		interpreter = 'powershell'
		encoded_script=base64.b64encode(
			command.script.encode("utf_16_le")).decode('cp850')
		#encoded_script=self.powershell_quote(command.script)
		cmd = "hostname;$u='{usr}';$p=ConvertTo-SecureString '{pw}' -AsPlainText -Force;$c = new-object -typename System.Management.Automation.PSCredential -args $u,$p;icm -cn {target} -authentication Negotiate -credential $c -command {{powershell -encodedcommand {script}}}".format(
			target=target.hostname,
			script=encoded_script,
			usr=target.data['username'],
			pw=target.data['password'])
		return Command(interpreter, cmd)

	def cmd_unix_win_winrm(self, command, initiator, target):
		interpreter = 'sh'
		cmd = "hostname;winrm-client ps {target} --creds {usr} {pw} {script}".format(
			target=target.hostname,
			script=self.bash_quote(command.script),
			usr=target.data['username'],
			pw=target.data['password'])
		return Command(interpreter, cmd)

	def cmd_win_unix_ssh(self, command, initiator, target):
		interpreter = 'powershell'
		cmd = "hostname;$K = [IO.Path]::GetTempFileName(); '{pk}'|out-file -encoding 'OEM' $K; ssh -I $K {usr}@{target} {script};rm $K; exit $LastExitCode".format(
			target=target.hostname,
			script = self.powershell_quote(command.script),
			usr=target.data['username'],
			pk=target.data['private_key'])
		return Command(interpreter, cmd)

	def cmd_unix_unix_ssh(self, command, initiator, target):
		interpreter = 'sh'
		cmd = "hostname;K=mktemp && echo '{pk}' >$K; ssh -I $K {usr}@{target} {script};R=$?;rm $K; exit $R".format(
			target=target.hostname,
			script = self.bash_quote(command.script),
			usr=target.data['username'],
			pk=target.data['private_key'])
		return Command(interpreter, cmd)

class Route(object):
	def __init__(self, hops):
		self.hops = hops
		self.wrapper=Wrapper()

	@classmethod
	def from_string(cls, hop_string="", hop_definition_provider={}):
		hop_list=list(filter(None, hop_string.split(';')))
		if len(hop_list) == 0:
			return cls([])
		try:
			return cls([Hop(hop_definition_provider[hop]) for hop in hop_list])
		except KeyError as e:
			hop = e.args[0]
			raise RouteError(
				"No hop definition found for '{hop}'".format(hop=hop))

	@classmethod
	def direct(cls):
		return cls([])

	def execute(self, target, command):
		try:
			hop_zero=self.wrapper.wrap(self, target, command)
		except WrapperError:
			raise
		if len(self.hops) > 0:
			print("On " + self.hops[0].hostname + ": " + str(hop_zero.cmd.script))
			print(len(hop_zero.cmd.script))
		else:
			print("On " + target.hostname + ": " + str(hop_zero.cmd.script))
			print("")


class ConfigFileHopDefinitionProvider(object):
	def __init__(self, config_file):
		pass

class DictionaryHopDefinitionProvider(object):
	def __init__(self, dictionary):
		self.dictionary=dictionary

	def __len__(self):
		return len(self.dictionary)

	def __getitem__(self, key):
		return self.dictionary[key]

class Hop(object):
	def __init__(self, data):
		self.hostname = data['hostname']
		self.system = data['system']
		self.protocol = data['protocol']
		self.data=data
		self.cmd = ''


class Command(object):
	def __init__(self, interpreter, script,
				 pre_script='', post_script=''):
		self.interpreter=interpreter
		self.script=script
		self.rc = -1
		self.stdout=''
		self.stderr=''


class WinRMSession(winrm.Session):
	def __init__(self, protocol):
		self.protocol = protocol

	@classmethod
	def SSL(cls, target, auth, verify=True):
		endpoint="https://{target}:5986/wsman".format(target=target)
		if isinstance(auth, CredentialsAuth):
			username, password = auth
			protocol = winrm.protocol(
				endpoint=endpoint,
				transport='ssl',
				server_cert_validation = 'validate' if verify else 'ignore',
				ca_trust_path = verify,
				username=username,
				password=password)
		elif isinstance(auth, CertificateAuth):
			certificate = auth
			protocol = winrm.protocol(
				endpoint=endpoint,
				transport='ssl',
				server_cert_validation = 'validate' if verify else 'ignore',
				ca_trust_path = verify,
				cert_pem=certificate,
				cert_key_pem=certificate)
		else:
			raise Exception("Unknown auth method")
		return cls(protocol)

	@classmethod
	def Plain(cls, target, auth):
		endpoint="http://{target}:5985/wsman".format(target=target)
		if isinstance(auth, CredentialsAuth):
			username, password = auth
			protocol = winrm.protocol(
				endpoint=endpoint,
				transport='plaintext',
				username=username,
				password=password)
		else:
			raise Exception("Unknown auth method")
		return cls(protocol)

	@classmethod
	def Ntlm(cls, target, auth):
		endpoint="http://{target}:5985/wsman".format(target=target)
		if isinstance(auth, CredentialsAuth):
			username, password = auth
			protocol = winrm.protocol(
				endpoint=endpoint,
				transport='ntlm',
				username=username,
				password=password)
		else:
			raise Exception("Unknown auth method")
		return cls(protocol)


class SSHSession(object):
	def __init__(self, target, auth):
		self.target=target
		self.auth=auth



class Auth(object):
	def __init__(self):
		raise NotImplementedError

	def __len__(self):
		raise NotImplementedError

	def __getitem__(self, key):
		raise NotImplementedError


class CertificateAuth(Auth):
	def __init__(self, auth_provider):
		self.client_certificate = auth_provider.get_client_certificate()

	def __len__(self):
		return 1

	def __getitem__(self, key):
		if key == 0:
			return self.client_certificate
		elif key != 0:
			raise IndexError
		elif not isinstance(key, int):
			raise TypeError


class CredentialsAuth(Auth):
	def __init__(self, auth_provider):
		self.username , self.password = auth_provider.get_credentials()

	def __len__(self):
		return 2

	def __getitem__(self, key):
		if key == 0:
			return self.username
		elif key == 1:
			return self.password
		elif key not in [0, 1]:
			raise IndexError
		elif not isinstance(key, int):
			raise TypeError


class PrivateKeyAuth(Auth):
	def __init__(self, auth_provider):
		self.username , self.ssh_private_key = auth_provider.get_private_key()

	def __len__(self):
		return 2

	def __getitem__(self, key):
		if key == 0:
			return self.username
		elif key == 1:
			return self.ssh_private_key
		elif key not in [0, 1]:
			raise IndexError
		elif not isinstance(key, int):
			raise TypeError

class AuthProvider(object):
	def __init__(self):
		raise NotImplementedError

class PlaintextAuthProvider(AuthProvider):
	def __init__(self, **kwargs):
		self.data = kwargs

	def get_credentials(self):
		try:
			return self.data['username'], self.data['password']
		except KeyError:
			raise AuthProviderError("No credentials available!")

	def get_private_key(self):
		try:
			return self.data['username'], self.data['private_key']
		except KeyError:
			raise AuthProviderError("No private key available!")

	def get_client_certificate(self):
		try:
			return self.data['username'], self.data['client_certificate']
		except KeyError:
			raise AuthProviderError("No client certificate available!")


class PMPAuthProvider(AuthProvider):
	def __init__(self, pmp_session, pmp_resource, pmp_account):
		self.pmp_session = pmp_session

	def get_credentials(self):
		try:
			return self.pmp_session.get_username(self.pmp_resource, self.pmp_account), self.pmp_session.get_password(self.pmp_resource, self.pmp_account)
		except PMPError as e:
			raise

	def get_private_key(self):
		try:
			return self.pmp_session.get_username(self.pmp_resource, self.pmp_account), self.pmp_session.get_private_key(
				self.pmp_resource, self.pmp_account)
		except PMPError as e:
			raise

	def get_client_certificate(self):
		try:
			return self.pmp_session.get_client_certificate(
				self.pmp_resource, self.pmp_account)
		except PMPError as e:
			raise

class AuthProviderError(Exception):
	def __init__(self, message):
		Exception.__init__(self, message)

class RouteError(Exception):
	def __init__(self, message):
		Exception.__init__(self, message)

class WrapperError(Exception):
	def __init__(self, message):
		Exception.__init__(self, message)
