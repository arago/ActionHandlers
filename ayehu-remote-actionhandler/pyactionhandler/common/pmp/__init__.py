import requests
import urlparse
import urllib
import json
import pprint
from docopt import docopt
from schema import Schema, Or, And, Optional, Use
import codecs
import schema
import sys
import re
import ConfigParser

from requests.packages.urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# baseurl decorator, adds baseurl to first positional argument
# or "url" keyword argument
def addBaseURL(function):
	def wrapper(self, *args, **kwargs):
		if args:
			args = (self._baseurl + args[0],)
		if 'url' in kwargs:
			kwargs['url'] = self._baseurl + kwargs['url']
		return function(self, *args, **kwargs)
	return wrapper

class ExtendByDecoratorMeta(type):
	def __new__(cls, name, bases, d):

		def not_implemented(*args, **kwargs):
			raise NotImplementedError('You called a function that is not'
			                          ' implemented!')

		# find method in base classes
		def find_method(m):
			for base in bases:
				try:
					return getattr(base, m)
				except AttributeError:
					pass
				if ('ignoreUnknownMethods' in d and
				    d['ignoreUnknownMethods']):
					return not_implemented
				else:
					raise AttributeError(
						"No bases have method '{}'".format(m))

		# decorate specified methods with given decorator
		for decorator in d['methodsToDecorate']:
			for method in d['methodsToDecorate'][decorator]:
				d[method] = decorator(find_method(method))
		return type(name, bases, d)

class PMPSession(requests.Session):
	__metaclass__ = ExtendByDecoratorMeta
	methodsToDecorate = {addBaseURL:['get','post', 'stub']}
	ignoreUnknownMethods = True

	def __init__(self, baseurl, *args, **kwargs):
		self._baseurl=baseurl
		super(PMPSession, self).__init__(*args, **kwargs)

	def __str__(self):
		return 'PMP at {url}'.format(url=self._baseurl)

class PMPCredentials(object):
	def __init__(self, Session, ResourceName, AccountName):
		try:
			response = Session.get("/resources/resourcename/{res}/accounts/accountname/{acc}".format(
				res=ResourceName,
				acc=AccountName
			))
			response.raise_for_status()
		except requests.exceptions.ConnectionError as e:
			print >>sys.stderr, "Cannot connect to PMP at {api}: {error}".format(
				api=Session._baseurl,
				error=e.message.reason.message)
			sys.exit(255)
		except requests.exceptions.HTTPError as e:
			if e.response.status_code == 404:
				print >>sys.stderr, "No PMP API at {api}".format(
					api=Session._baseurl)
				sys.exit(255)
		data = json.loads(response.content)
		if data['operation']['result']['status'] != "Success":
			print >>sys.stderr, u"Querying PMP for account '{acc}' on resource '{res}' failed: {reason}".format(
				acc=AccountName,
				res=ResourceName,
				reason=data['operation']['result']['message'])
			sys.exit(255)
		self.Session=Session
		self.ResourceName=ResourceName
		self.AccountName=AccountName
		try:
			self.ResourceID=data[u'operation'][u'Details'][u'RESOURCEID']
			self.AccountID=data[u'operation'][u'Details'][u'ACCOUNTID']
		except KeyError as e:
			print >>sys.stderr, "Account '{acc}' for Resource '{res}' not found!".format(
				acc=AccountName,
				res=ResourceName)
			sys.exit(255)
		try:
			response2 = Session.get("/resources/{res_id}/accounts".format(
				res_id=self.ResourceID,
			))
			response.raise_for_status()
		except requests.exceptions.ConnectionError as e:
			print >>sys.stderr, "Cannot connect to PMP at {api}: {error}".format(
				api=Session._baseurl,
				error=e.message.reason.message)
			sys.exit(255)
		except requests.exceptions.HTTPError as e:
			if e.response.status_code == 404:
				print >>sys.stderr, "No PMP API at {api}".format(
					api=Session._baseurl)
				sys.exit(255)
		data2 = json.loads(response2.content)
		if data['operation']['result']['status'] != "Success":
			print >>sys.stderr, u"Querying PMP for resource '{res}' failed: {reason}".format(
				res=ResourceName,
				reason=data['operation']['result']['message'])
			sys.exit(255)
		try:
			self.ResourceType=data2[u'operation'][u'Details'][u'RESOURCE TYPE']
			self.ResourceDNSName=data2[u'operation'][u'Details'][u'DNS NAME']
		except KeyError as e:
			print >>sys.stderr, "Account '{acc}' for Resource '{res}' not found!".format(
				acc=AccountName,
				res=ResourceName)
			sys.exit(255)
		if self.ResourceType == "Windows":
			self.WindowsUserName = ".\\" + AccountName
		elif self.ResourceType == "WindowsDomain":
			self.WindowsUserName = self.ResourceDNSName.split(".")[0] + "\\" + AccountName

	def passwd(self):
		"""Possible performance fix: Get the password from the second rest call in the constructor and save it for later"""
		try:
			r = self.Session.get("/resources/{res_id}/accounts/{acc_id}/password".format(res_id=self.ResourceID, acc_id=self.AccountID))
			r.raise_for_status()
			return json.loads(r.content)[u'operation'][u'Details'][u'PASSWORD']
		except requests.exceptions.HTTPError as e:
			print e.message

	def get_file(self, filetype):
		try:
			r = self.Session.get("/resources/{res_id}/accounts/{acc_id}/downloadfile".format(res_id=self.ResourceID, acc_id=self.AccountID), params={"INPUT_DATA":"{{\"operation\":{{\"Details\":{{\"ISCUSTOMFIELD\":\"TRUE\",\"CUSTOMFIELDTYPE\":\"ACCOUNT\",\"CUSTOMFIELDLABEL\":\"{field}\"}}}}}}".format(field=filetype)})
			r.raise_for_status()
			return r.content
		except requests.exceptions.HTTPError as e:
			print e.message
			sys.exit(255)
		except requests.exceptions.ConnectionError as e:
			if re.search("HTTP/1.1 1000", e.message.args[1].line):
				print "Account '{acc}' on resource '{res}' has no file {filename}".format(
					acc=self.AccountName,
					res=self.ResourceName,
					filename=filetype)
			sys.exit(255)

	def ssh_key(self):
		return self.get_file("ssh_private_key")

	def ssl_cert(self):
		return self.get_file("ssl_client_certificate")

	def ssl_key(self):
		return self.get_file("ssl_client_certificate_key")


class TokenAuth(requests.auth.AuthBase):
	def __init__(self, Token):
		self._token=Token

	def __call__(self, r):
		parsed = urlparse.urlparse(r.url)
		params = urlparse.parse_qs(parsed.query)
		params["AUTHTOKEN"] = self._token
		newquery=r._encode_params(params)
		replaced = parsed._replace(query=newquery)
		r.url = urlparse.urlunparse(replaced)
		return r

def copyf(dictlist, key, valuelist):
	return [dictio for dictio in dictlist if dictio[key] in valuelist]



if __name__ == '__main__':
	sys.stdout = codecs.getwriter('utf8')(sys.stdout)
	sys.stderr = codecs.getwriter('utf8')(sys.stderr)

	usage="""
Usage:
  pmp-client [options] (passwd|ssh_key|cert|cert_key) <resource> <account>

Commands:
  passwd                     Get the password
  ssh_key                    Get the SSH private key
  cert                       Get the SSL client certificate
  cert_key                   Get the key to the SSL client certificate

Arguments:
  <resouce>                  Name of the PMP resource
  <account>                  Name of the account

Options:
  --pmp_inst=<pmp_instance>  Name of the PMP instance [default: default]
  -h --help                  Print this help message and exit
"""
	s = Schema({"<resource>":     And(str),
	            "<account>":      And(str),
	            # suppress validation errors for additional elements
	            Optional(object): object
	})
	try:
		args = s.validate(docopt(usage))
	except schema.SchemaError as e:
		print >>sys.stderr, usage
		print >>sys.stderr, e
		sys.exit(255)

	config = ConfigParser.ConfigParser()
	config.read('/opt/autopilot/conf/pmp.conf')

	s = PMPSession(config.get(args['--pmp_inst'], 'URL'))
	s.auth = TokenAuth(config.get(args['--pmp_inst'], 'Token'))
	s.verify=False

	a = PMPCredentials(s, ResourceName=args['<resource>'], AccountName=args['<account>'])

	if args['passwd']:
		print a.passwd()
	elif args['ssh_key']:
		print a.ssh_key()
	elif args['cert']:
		print a.ssl_cert()
	elif args['cert_key']:
		print a.ssl_key()


