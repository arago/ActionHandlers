import requests
import urllib.parse as urlparse
import re
from pyactionhandler.common.pmp.exceptions import PMPError, PMPConnectionError
from pyactionhandler.common.pmp.helpers import memoize
from pyactionhandler.helper import addBaseURL
from pyactionhandler.meta import ExtendByDecoratorMeta

from requests.packages.urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

class PMPSession(requests.Session, metaclass=ExtendByDecoratorMeta, methodsToDecorate = {addBaseURL:['get']}, ignoreUnknownMethods = False):

	def __init__(self, baseurl, *args, **kwargs):
		self._baseurl=baseurl
		super(PMPSession, self).__init__(*args, **kwargs)

	def __str__(self):
		return 'PMP at {url}'.format(url=self._baseurl)

	@memoize
	def get_ids(self, pmp_resource, pmp_account):
		try:
			response = self.get("/resources/resourcename/{res}/accounts/accountname/{acc}".format(
				res=pmp_resource,
				acc=pmp_account
			))
			response.raise_for_status()
		except requests.exceptions.ConnectionError as e:
			raise PMPConnectionError(
				"Cannot connect to PMP at {api}: {error}".format(
					api=self._baseurl,
					error=e.message.reason.message))
		except requests.exceptions.HTTPError as e:
			if e.response.status_code == 404:
				raise PMPConnectionError(
					"No PMP API at {api}".format(api=self._baseurl))
		data = response.json()
		if data['operation']['result']['status'] != "Success":
			raise PMPError(
				"Querying PMP for account '{acc}' on resource '{res}' failed: {reason}".format(
					acc=pmp_account,
					res=pmp_resource,
					reason=data['operation']['result']['message']))
		try:
			return data[u'operation'][u'Details'][u'RESOURCEID'], data[u'operation'][u'Details'][u'ACCOUNTID']
		except KeyError as e:
			raise PMPError(
				"Account '{acc}' for Resource '{res}' not found!".format(
					acc=pmp_account,
					res=pmp_resource))

	@memoize
	def get_account_data(self, pmp_resource, pmp_account):
		pmp_resource_id, pmp_account_id = self.get_ids(
			pmp_resource, pmp_account)
		try:
			response = self.get("/resources/{res_id}/accounts".format(
				res_id=pmp_resource_id,
			))
			response.raise_for_status()
		except requests.exceptions.ConnectionError as e:
			raise PMPConnectionError(
				"Cannot connect to PMP at {api}: {error}".format(
					api=self._baseurl,
					error=e.message.reason.message))
		except requests.exceptions.HTTPError as e:
			if e.response.status_code == 404:
				raise PMPConnectionError(
					"No PMP API at {api}".format(api=self._baseurl))
		data = response.json()
		if data['operation']['result']['status'] != "Success":
			raise PMPError(
				"Querying PMP for resource '{res}' failed: {reason}".format(
					res=pmp_resource,
					reason=data['operation']['result']['message']))
		else:
			return data

	def get_file(self, pmp_resource, pmp_account, filetype=None):
		pmp_resource_id, pmp_account_id = self.get_ids(
			pmp_resource, pmp_account)
		try:
			if filetype:
				r = self.Session.get("/resources/{res_id}/accounts/{acc_id}/downloadfile".format(res_id=pmp_resource_id, acc_id=pmp_account_id), params={"INPUT_DATA":"{{\"operation\":{{\"Details\":{{\"ISCUSTOMFIELD\":\"TRUE\",\"CUSTOMFIELDTYPE\":\"ACCOUNT\",\"CUSTOMFIELDLABEL\":\"{field}\"}}}}}}".format(field=filetype)})
			else:
				r = self.Session.get("/resources/{res_id}/accounts/{acc_id}/downloadfile".format(res_id=pmp_resource_id, acc_id=pmp_account_id))
			r.raise_for_status()
			return r.content
		except requests.exceptions.HTTPError as e:
			raise PMPError(e.message)
		except requests.exceptions.ConnectionError as e:
			if re.search("HTTP/1.1 1000", e.message.args[1].line):
				raise PMPError(
					"Account '{acc}' on resource '{res}' has no file {filename}".format(
						acc=pmp_account,
						res=pmp_resource,
						filename=filetype))

	def get_password(self, pmp_resource, pmp_account):
		pmp_resource_id, pmp_account_id = self.get_ids(
			pmp_resource, pmp_account)
		try:
			r = self.Session.get("/resources/{res_id}/accounts/{acc_id}/password".format(res_id=pmp_resource_id, acc_id=pmp_account_id))
			r.raise_for_status()
			return r.json()[u'operation'][u'Details'][u'PASSWORD']
		except requests.exceptions.HTTPError as e:
			raise PMPError(e.message)

	def get_private_key(self, pmp_resource, pmp_account):
		pmp_resource_id, pmp_account_id = self.get_ids(
			pmp_resource, pmp_account)
		return self.get_file(pmp_resource_id, pmp_account_id, "ssh_private_key")

	def get_client_certificate(self, pmp_resource, pmp_account):
		pmp_resource_id, pmp_account_id = self.get_ids(
			pmp_resource, pmp_account)
		return self.get_file(pmp_resource_id, pmp_account_id, "ssl_client_certificate")

	def get_resource_type(self, pmp_resource, pmp_account):
		data = self.get_account_data(pmp_resource, pmp_account)
		try:
			return data[u'operation'][u'Details'][u'RESOURCE TYPE']
		except KeyError as e:
			raise PMPError(
				"Account '{acc}' for Resource '{res}' has no resource type!".format(
					acc=pmp_account,
					res=pmp_resource))

	def get_resource_dnsname(self, pmp_resource, pmp_account):
		data = self.get_account_data(pmp_resource, pmp_account)
		try:
			return data[u'operation'][u'Details'][u'DNS NAME']
		except KeyError as e:
			raise PMPError(
				"Account '{acc}' for Resource '{res}' has no DNS name!".format(
					acc=pmp_account,
					res=pmp_resource))

	def get_username(self, pmp_resource, pmp_account):
		pmp_resource_type = self.get_resource_type(pmp_resource, pmp_account)
		pmp_resource_dnsname = self.get_resource_dnsname(pmp_resource, pmp_account)
		if pmp_resource_type == "Windows":
			return ".\\" + pmp_account
		elif pmp_resource_type == "WindowsDomain":
			return pmp_resource_dnsname.split(".")[0] + "\\" + pmp_account
		else:
			return pmp_account


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
