import zmq.green as zmq
from arago.pyactionhandler.protobuf.CommonTypes_pb2 import StringMessage, StringResponse, StringOrErrorResponse, BooleanMessage, GetAttributeRequest, SetAttributeRequest
from arago.pyactionhandler.protobuf.IssueAPI_pb2 import IssueHistoryEntryMessage
from arago.common.helper import encode_rpc_call
from lxml import etree
from gevent.lock import BoundedSemaphore
import time


class IssueNotFoundError(Exception):
	pass
class AttribNotFoundError(Exception):
	pass
class ResolveFailedError(Exception):
	pass
class SetAttributeFailedError(Exception):
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

	def add_issue_history_entry(self, iid, kiid, nodeid, element_message,
								element_name="External",  timestamp=None, loglevel=2):
		rpc_call = encode_rpc_call("IssueAPI_Service", "AddHistoryEntry", "5.4")
		req = IssueHistoryEntryMessage()
		req.timestamp = timestamp or int(time.time() * 1000)
		req.ki_id = kiid
		req.node_id = nodeid
		req.element_name = element_name
		req.element_message = element_message
		req.log_level = loglevel
		req.issueid = iid
		with self._lock:
			self.socket.send_multipart((b'sah', rpc_call, req.SerializeToString()))
			id1, svc_call, payload = self.socket.recv_multipart()
		resp = BooleanMessage()
		resp.ParseFromString(payload)
		return resp

	def get_attribute(self, iid, attrib):
		rpc_call = encode_rpc_call("IssueAPI_Service", "GetAttribute", "5.4")
		req = GetAttributeRequest()
		req.nodeid = iid
		req.parentuid=""
		req.attr = attrib
		with self._lock:
			self.socket.send_multipart((b'sah', rpc_call, req.SerializeToString()))
			id1, svc_call, payload = self.socket.recv_multipart()
		resp = StringResponse()
		resp.ParseFromString(payload)
		if not resp.success:
			raise AttribNotFoundError()
		return resp.value

	def set_attribute(self, iid, attrib, value):
		rpc_call = encode_rpc_call("IssueAPI_Service", "SetAttribute", "5.4")
		req = SetAttributeRequest()
		req.nodeid = iid
		req.parentuid=""
		req.attr = attrib
		req.value = value
		with self._lock:
			self.socket.send_multipart((b'sah', rpc_call, req.SerializeToString()))
			id1, svc_call, payload = self.socket.recv_multipart()
		resp = BooleanMessage()
		resp.ParseFromString(payload)
		if not resp.value:
			raise SetAttributeFailedError()

	def resolve(self, iid):
		rpc_call = encode_rpc_call("IssueAPI_Service", "Resolve", "5.4")
		req = StringMessage()
		req.value = iid
		with self._lock:
			self.socket.send_multipart((b'sah', rpc_call, req.SerializeToString()))
			id1, svc_call, payload = self.socket.recv_multipart()
		resp = StringResponse()
		resp.ParseFromString(payload)
		if not resp.success:
			raise ResolveFailedError(resp.value)
