import gevent
import zmq.green as zmq
from greenlet import GreenletExit
import greenlet
from pyactionhandler.helper import decode_rpc_call
from pyactionhandler.exceptions import DecodeRPCError
from pyactionhandler.protobuf.ActionHandler_pb2 import ActionRequest, ActionResponse
import logging

class SyncHandler(object):
	def __init__(self, worker_collection, zmq_url):
		self.logger = logging.getLogger('actionhandler')
		self.shutdown=False
		self.worker_collection=worker_collection
		self.zmq_url=zmq_url
		self.zmq_ctx = zmq.Context()
		self.zmq_socket = self.zmq_ctx.socket(zmq.ROUTER)
		self.zmq_socket.bind(self.zmq_url)
		self.response_queue=gevent.queue.JoinableQueue(maxsize=0)
		self.worker_collection.register_response_queue(
			self.response_queue)

	def next_request(self):
		id1, id2, svc_call, params = self.zmq_socket.recv_multipart()
		try:
			service, method = decode_rpc_call(svc_call)
			req=ActionRequest()
			req.ParseFromString(params)
			params_dict = {param.key: param.value for param in req.params_list}
			self.logger.debug("Decoded RPC message")
			return (req.capability,
				req.time_out,
				params_dict,
				(id1, id2, svc_call))
		except (DecodeRPCError)  as e:
			self.logger.error("Could not decode RPC message")
			raise

	def handle_requests(self):
		try:
			self.logger.info("Started handling requests")
			while not self.shutdown:
				try:
					capability, timeout, params, zmq_info = self.next_request()
				except (DecodeRPCError):
					continue
				self.worker_collection.task_queue.put(
					(capability, timeout, params, zmq_info))
				self.logger.debug(
					"Put Action on ActionHandler request queue, %d unfinished tasks" % self.worker_collection.task_queue.unfinished_tasks)
		except GreenletExit as e:
			## Block all further incoming messages
			self.logger.info("Stopped handling requests")

	def handle_responses(self):
		try:
			self.logger.info("Started handling responses")
			while True:
				action=self.response_queue.get()
				id1, id2, svc_call = action.zmq_info
				resp=ActionResponse()
				resp.output = action.output
				resp.error_text = action.error_output
				resp.system_rc = action.system_rc
				resp.statusmsg = action.statusmsg
				resp.success = action.success
				self.zmq_socket.send_multipart((id1, id2, svc_call, resp.SerializeToString()))
				self.worker_collection.task_queue.task_done()
				del id1, id2, svc_call, resp
				self.response_queue.task_done()
				self.logger.debug(
					"Removed Action from ActionHandler response queue, %d unfinished tasks" % self.worker_collection.task_queue.unfinished_tasks)
		except GreenletExit as e:
			self.logger.info("Stopped handling responses")

