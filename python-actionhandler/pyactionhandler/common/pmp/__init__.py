import requests
import urllib.parse as urlparse
import urllib
import json
import codecs
import re
from pyactionhandler.common.pmp.exceptions import PMPError, PMPConnectionError
from pyactionhandler.helper import addBaseURL
from pyactionhandler.meta import ExtendByDecoratorMeta

from requests.packages.urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

class PMPSession(requests.Session, metaclass=ExtendByDecoratorMeta, methodsToDecorate = {addBaseURL:['get','post', 'stub']}, ignoreUnknownMethods = True):

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
			raise PMPConnectionError(
				"Cannot connect to PMP at {api}: {error}".format(
					api=Session._baseurl,
					error=e.message.reason.message))
		except requests.exceptions.HTTPError as e:
			if e.response.status_code == 404:
				raise PMPConnectionError(
					"No PMP API at {api}".format(api=Session._baseurl))
		data = response.json()
		if data['operation']['result']['status'] != "Success":
			raise PMPError(
				"Querying PMP for account '{acc}' on resource '{res}' failed: {reason}".format(
					acc=AccountName,
					res=ResourceName,
					reason=data['operation']['result']['message']))
		self.Session=Session
		self.ResourceName=ResourceName
		self.AccountName=AccountName
		try:
			self.ResourceID=data[u'operation'][u'Details'][u'RESOURCEID']
			self.AccountID=data[u'operation'][u'Details'][u'ACCOUNTID']
		except KeyError as e:
			raise PMPError(
				"Account '{acc}' for Resource '{res}' not found!".format(
					acc=AccountName,
					res=ResourceName))
		try:
			response2 = Session.get("/resources/{res_id}/accounts".format(
				res_id=self.ResourceID,
			))
			response.raise_for_status()
		except requests.exceptions.ConnectionError as e:
			raise PMPConnectionError(
				"Cannot connect to PMP at {api}: {error}".format(
					api=Session._baseurl,
					error=e.message.reason.message))
		except requests.exceptions.HTTPError as e:
			if e.response.status_code == 404:
				raise PMPConnectionError(
					"No PMP API at {api}".format(api=Session._baseurl))
		data2 = response2.json()
		if data['operation']['result']['status'] != "Success":
			raise PMPError(
				"Querying PMP for resource '{res}' failed: {reason}".format(
					res=ResourceName,
					reason=data['operation']['result']['message']))
		try:
			self.ResourceType=data2[u'operation'][u'Details'][u'RESOURCE TYPE']
			self.ResourceDNSName=data2[u'operation'][u'Details'][u'DNS NAME']
		except KeyError as e:
			raise PMPError(
				"Account '{acc}' for Resource '{res}' not found!".format(
					acc=AccountName,
					res=ResourceName))
		if self.ResourceType == "Windows":
			self.WindowsUserName = ".\\" + AccountName
		elif self.ResourceType == "WindowsDomain":
			self.WindowsUserName = self.ResourceDNSName.split(".")[0] + "\\" + AccountName

	def passwd(self):
		"""Possible performance fix: Get the password from the second rest call in the constructor and save it for later"""
		try:
			r = self.Session.get("/resources/{res_id}/accounts/{acc_id}/password".format(res_id=self.ResourceID, acc_id=self.AccountID))
			r.raise_for_status()
			return r.json()[u'operation'][u'Details'][u'PASSWORD']
		except requests.exceptions.HTTPError as e:
			raise PMPError(e.message)

	def get_file(self, filetype=None):
		try:
			if filetype:
				r = self.Session.get("/resources/{res_id}/accounts/{acc_id}/downloadfile".format(res_id=self.ResourceID, acc_id=self.AccountID), params={"INPUT_DATA":"{{\"operation\":{{\"Details\":{{\"ISCUSTOMFIELD\":\"TRUE\",\"CUSTOMFIELDTYPE\":\"ACCOUNT\",\"CUSTOMFIELDLABEL\":\"{field}\"}}}}}}".format(field=filetype)})
			else:
				r = self.Session.get("/resources/{res_id}/accounts/{acc_id}/downloadfile".format(res_id=self.ResourceID, acc_id=self.AccountID))
			r.raise_for_status()
			return r.content
		except requests.exceptions.HTTPError as e:
			raise PMPError(e.message)
		except requests.exceptions.ConnectionError as e:
			if re.search("HTTP/1.1 1000", e.message.args[1].line):
				raise PMPError(
					"Account '{acc}' on resource '{res}' has no file {filename}".format(
						acc=self.AccountName,
						res=self.ResourceName,
						filename=filetype))

	@property
	def ssh_key(self):
		return self.get_file("ssh_private_key")

	@property
	def ssl_cert(self):
		return self.get_file("ssl_client_certificate")


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
