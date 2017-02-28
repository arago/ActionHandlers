import requests
import urllib.parse as urlparse
from pyactionhandler.helper import addBaseURL
from pyactionhandler.meta import ExtendByDecoratorMeta

from requests.packages.urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

class Krb5Session(requests.Session, metaclass=ExtendByDecoratorMeta, methodsToDecorate = {addBaseURL:['get']}, ignoreUnknownMethods = False):

	def __init__(self, baseurl, *args, **kwargs):
		self._baseurl=baseurl
		super(Krb5Session, self).__init__(*args, **kwargs)

	def __str__(self):
		return 'Kerberos'

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
