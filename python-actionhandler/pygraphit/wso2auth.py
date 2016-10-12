import sys
import requests
import requests.auth
import logging
import time
from pygraphit.exceptions import WSO2Error, WSO2TokenRenewalError

class WSO2AuthPW(requests.auth.AuthBase):
	def __init__(self, url=None, auth=None, client=None, verify=True):
		self._url = url
		self._verify = verify
		username, password = auth
		self._client_id, self._client_secret = client
		self.logger=logging.getLogger('root')
		basic_auth = requests.auth.HTTPBasicAuth(self._client_id,
		                                         self._client_secret)
		post_data = {"grant_type": "password",
		             "username": username,
		             "password": password}
		headers = {"User-Agent": "PyGraphIT/1.0",
		           "Content-Type": "application/x-www-form-urlencoded",
		           "charset": "UTF-8"}
		try:
			r = requests.post(self._url + "/oauth2/token",
			                  auth=basic_auth,
			                  data=post_data,
			                  headers=headers,
			                  verify=self._verify)
			r.raise_for_status()
		except requests.exceptions.HTTPError as e:
			raise WSO2Error(e)
		self._token = Token(r.json())

	def renew_token(self):
		post_data = {"grant_type": "refresh_token",
		             "client_id": self._client_id,
		             "client_secret": self._client_secret,
		             "refresh_token": self._token.refresh_token}
		headers = {"User-Agent": "RESTClient/0.1",
		           "Content-Type": "application/x-www-form-urlencoded",
		           "charset": "UTF-8"}
		try:
			r = requests.post(self._url + "/oauth2/token",
			                  data=post_data,
			                  headers=headers,
			                  verify=self._verify)
			r.raise_for_status()
		except requests.exceptions.HTTPError as e:
			raise WSO2Error(e)
		self._token = Token(r.json())
		self.logger.debug("Checking new token validity")
		try:
			headers['Authorization']="Bearer {token}".format(
				token=self._token.access_token)
			r = requests.get(self._url + "/oauth2/userinfo?schema=openid",
							headers=headers,
							verify=self._verify)
			r.raise_for_status()
		except requests.exceptions.HTTPError as e:
			if e.response.json()['error'] == 'invalid_token':
				raise WSO2TokenRenewalError("Refreshing Token failed")

	def __str__(self):
		str = "Token expires in {exp} seconds."
		return str.format(exp=int(self._token.expires_in))

	def __call__(self, r):
		self.logger.debug("Inserting OAuth token into request header.")
		r.headers['_TOKEN'] = self._token.access_token
		return r

class WSO2AuthCC(WSO2AuthPW):
	def __init__(self, url=None, client=None, verify=True):
		self._url = url
		self._verify = verify
		self._client_id, self._client_secret = client
		self.logger=logging.getLogger('root')
		basic_auth = requests.auth.HTTPBasicAuth(self._client_id,
		                                         self._client_secret)
		post_data = {"grant_type": "client_credentials"}
		headers = {"User-Agent": "PyGraphIT/1.0",
		           "Content-Type": "application/x-www-form-urlencoded",
		           "charset": "UTF-8"}
		try:
			r = requests.post(self._url + "/oauth2/token",
			                  auth=basic_auth,
			                  data=post_data,
			                  headers=headers,
			                  verify=self._verify)
			r.raise_for_status()
		except requests.exceptions.HTTPError as e:
			raise WSO2Error(e)
		self._token = Token(r.json())

	def renew_token(self):
		basic_auth = requests.auth.HTTPBasicAuth(self._client_id,
		                                         self._client_secret)
		post_data = {"grant_type": "client_credentials"}
		headers = {"User-Agent": "PyGraphIT/1.0",
		           "Content-Type": "application/x-www-form-urlencoded",
		           "charset": "UTF-8"}
		try:
			r = requests.post(self._url + "/oauth2/token",
			                  auth=basic_auth,
			                  data=post_data,
			                  headers=headers,
			                  verify=self._verify)
			r.raise_for_status()
		except requests.exceptions.HTTPError as e:
			raise WSO2Error(e)
		self._token = Token(r.json())
		self.logger.debug("Checking new token validity")
		try:
			headers['Authorization']="Bearer {token}".format(
				token=self._token.access_token)
			r = requests.get(self._url + "/oauth2/userinfo?schema=openid",
							headers=headers,
							verify=self._verify)
			r.raise_for_status()
		except requests.exceptions.HTTPError as e:
			if e.response.json()['error'] == 'invalid_token':
				raise WSO2TokenRenewalError("Refreshing Token failed")

class Token(object):
	def __init__(self, t):
		self.access_token = t['access_token']
		self.expires_at = t['expires_in'] + time.time()
		if 'refresh_token' in t:
			self.refresh_token = t['refresh_token']

	@property
	def expires_in(self):
		return int(self.expires_at - time.time())
