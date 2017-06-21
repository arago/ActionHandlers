import zmq.green as zmq
from arago.pyactionhandler.protobuf.CommonTypes_pb2 import StringMessage, StringResponse, StringOrErrorResponse
from arago.pyactionhandler.protobuf.IssueAPI_pb2 import IssueHistoryEntryMessage
from arago.common.helper import encode_rpc_call
from lxml import etree
from gevent.lock import BoundedSemaphore


class IssueNotFoundError(Exception):
	pass

class IssueAPI(object):
	def __init__(self, zmq_url):
		self.socket = zmq.Context().socket(zmq.DEALER)
		self.socket.connect(zmq_url)
		self._lock = BoundedSemaphore()

	def get_issue_data(self, iid, attribs=True, variables=True):
		xml = self.get_issue_xml(iid)
		xml = xml.replace(
			'xmlns="https://graphit.co/schemas/v2/IssueSchema"',
			'xmlnamespace="https://graphit.co/schemas/v2/IssueSchema"')
		r = etree.fromstring(xml)
		issue_attribs = dict(r.attrib)
		issue_variables = {}
		for item in r.findall(".//Content"):
			if item.getparent().tag in issue_variables:
				issue_variables[item.getparent().tag].append(item.attrib['Value'])
			else:
				issue_variables[item.getparent().tag] = [item.attrib['Value']]
		if attribs and variables:
			return issue_attribs, issue_variables
		elif attribs and not variables:
			return issue_attribs
		elif not attribs and variables:
			return issue_variables

	def get_issue_attribs(self, iid):
		return self.get_issue_data(iid, variables=False)

	def get_issue_variables(self, iid):
		return self.get_issue_data(iid, attribs=False)

	def get_issue_xml(self, iid):
		rpc_call = encode_rpc_call("IssueAPI_Service", "Read", "5.4")
		req = StringMessage()
		req.value=iid
		with self._lock:
			self.socket.send_multipart((b'sah', rpc_call, req.SerializeToString()))
			id1, svc_call, payload = self.socket.recv_multipart()
		resp = StringOrErrorResponse()
		resp.ParseFromString(payload)
		if resp.success:
			return resp.value
		else:
			raise IssueNotFoundError("Issue {iid} not found".format(iid=iid))

	def get_issue_history(self, iid):
		rpc_call = encode_rpc_call("IssueAPI_Service", "GetHistory", "5.4")
		req = StringMessage()
		req.value=iid
		with self._lock:
			self.socket.send_multipart((b'sah', rpc_call, req.SerializeToString()))
			history = []
			while True:
				id1, svc_call, payload = self.socket.recv_multipart()
				resp = IssueHistoryEntryMessage()
				resp.ParseFromString(payload)
				if not resp.element_name:
					break
				history.append(resp)
		return history
