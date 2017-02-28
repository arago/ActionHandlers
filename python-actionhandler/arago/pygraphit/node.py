import requests
import json
import logging
from urllib.parse import quote_plus
from pygraphit.exceptions import GraphitError, WSO2TokenRenewalError

class GraphitNode(object):
	def __init__(self, Session, nodeId, nodeType, nodeBody):
		self.session = Session
		self.nodeId = nodeId
		self.nodeType = nodeType
		self.nodeBody = nodeBody
		self.logger=logging.getLogger('root')

	def __str__(self):
		return str(self.nodeBody)

	def push(self, create=False):
		while True:
			try:
				r = self.session.post("/{nodeId}".format(
					nodeId=quote_plus(self.nodeId)),
					data = json.dumps(self.nodeBody))
				r.raise_for_status()
			except requests.exceptions.HTTPError as e:
				if e.response.json()['error'][
						'message'] == 'token invalid':
					self.logger.debug("WSO2 token expired, renewing ...")
					self.session.auth.renew_token()
				else:
					raise GraphitError(
						self.session,
						e.response.json()['error']['message'])
			except requests.exceptions.ConnectionError as e:
				raise GraphitError(self.session, e)
			else:
				return

	def pull(self):
		while True:
			try:
				r = self.session.get('/{nodeId}'.format(
					nodeId=quote_plus(self.nodeId)))
				r.raise_for_status()
				self.nodeBody=r.json()
			except requests.exceptions.HTTPError as e:
				if e.response.json()['error'][
						'message'] == 'token invalid':
					self.logger.debug("WSO2 token expired, renewing ...")
					self.session.auth.renew_token()
				else:
					raise GraphitError(
						self.session,
						e.response.json()['error']['message'])
			except requests.exceptions.ConnectionError as e:
				raise GraphitError(self.session, e)
			else:
				return

	def update(self, nodeBody):
		self.nodeBody=nodeBody
		self.push()

	def delete(self):
		raise NotImplementedError

	@classmethod
	def create(cls, Session, nodeType, nodeBody):
		while True:
			try:
				r = Session.post('/new/{type}'.format(
					type=quote_plus(nodeType)),
					data = json.dumps(nodeBody))
				r.raise_for_status()
			except requests.exceptions.HTTPError as e:
				if e.response.json()['error'][
						'message'] == 'token invalid':
					logging.getLogger('root').debug(
						"WSO2 token expired, renewing ...")
					Session.auth.renew_token()
				else:
					raise GraphitError(
						Session,
						e.response.json()['error']['message'])
			except requests.exceptions.ConnectionError as e:
				raise GraphitError(Session, e)
			else:
				body = r.json()
				nodeId = body['ogit/_id']
				return cls(Session, nodeId, nodeType, body)

	@classmethod
	def read(cls, Session, nodeId):
		while True:
			try:
				r = Session.get('/{nodeId}'.format(
					nodeId=quote_plus(nodeId)))
				r.raise_for_status()
			except requests.exceptions.HTTPError as e:
				if e.response.json()['error'][
						'message'] == 'token invalid':
					logging.getLogger('root').debug(
						"WSO2 token expired, renewing ...")
					Session.auth.renew_token()
				else:
					raise GraphitError(
						Session,
						e.response.json()['error']['message'])
			except requests.exceptions.ConnectionError as e:
				raise GraphitError(Session, e)
			else:
				body = r.json()
				nodeType = body['ogit/_type']
				return cls(Session, nodeId, nodeType, body)
