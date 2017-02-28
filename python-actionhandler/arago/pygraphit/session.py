import requests
from pygraphit.helper import addBaseURL
from pygraphit.meta import ExtendByDecoratorMeta

class GraphitSession(requests.Session,metaclass=ExtendByDecoratorMeta, methodsToDecorate = {addBaseURL:['get','post', 'stub']}, ignoreUnknownMethods = True):
	methodsToDecorate = {addBaseURL:['get','post', 'stub']}
	ignoreUnknownMethods = True

	def __init__(self, baseurl, *args, **kwargs):
		self._baseurl=baseurl
		super(GraphitSession, self).__init__(*args, **kwargs)

	def __str__(self):
		return 'GraphIT at {url}'.format(url=self._baseurl)
