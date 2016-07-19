import gevent
import zmq.green as zmq
from greenlet import GreenletExit
import greenlet
from pyactionhandler.helper import decode_rpc_call
from pyactionhandler.protobuf.ActionHandler_pb2 import ActionRequest, ActionResponse

class SyncHandler(object):
	def __init__(self, action_classes, worker_collection, zmq_url):
		self.shutdown=False
		self.action_classes=action_classes
		self.worker_collection=worker_collection
		self.zmq_url=zmq_url
		self.zmq_ctx = zmq.Context()
		self.zmq_socket = self.zmq_ctx.socket(zmq.ROUTER)
		self.zmq_socket.bind(self.zmq_url)
		self.request_queue=gevent.queue.JoinableQueue(maxsize=3)
		self.response_queue=gevent.queue.JoinableQueue(maxsize=0)

	def next_request(self):
		id1, id2, svc_call, params = self.zmq_socket.recv_multipart()
		try:
			service, method = decode_rpc_call(svc_call)
			req=ActionRequest()
			req.ParseFromString(params)
			params_dict = {param.key: param.value for param in req.params_list}
		except (DecodeRPCError)  as e:
			print("ERROR")
			print(e)
		return (req.capability,
				req.time_out,
				params_dict,
				(id1, id2, svc_call))

	def handle_requests(self):
		try:
			print("Started handling requests")
			while not self.shutdown:
				if self.request_queue.unfinished_tasks >= 3:
					gevent.idle()
					continue
				capability, timeout, params, zmq_info = self.next_request()
				print("putting action on overall queue")
				self.request_queue.put((capability, timeout, params, zmq_info))
				print(self.request_queue.unfinished_tasks)
		except GreenletExit as e:
			## Block all further incoming messages
			print("Stopped handling requests")

	def handle_requests_per_worker(self):
		try:
			print("Started handling requests")
			while not self.shutdown:
				capability, timeout, params, zmq_info = self.request_queue.get()
				print("putting action on worker queue")
				try:
					self.worker_collection.get_worker(
						params['NodeID'], self.response_queue).add_action(
							self.action_classes[capability][0](
								params['NodeID'],
								zmq_info,
								timeout,
								params,
								**self.action_classes[capability][1]))
				except KeyError:
					print("Unknown capability")
		except GreenletExit as e:
			## Block all further incoming messages
			print("Stopped handling requests")

	def handle_responses(self):
		try:
			print("Started handling responses")
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
				self.request_queue.task_done()
				del id1, id2, svc_call, resp
				print("removing action from overall queue")
				self.response_queue.task_done()
				print(self.request_queue.unfinished_tasks)
		except GreenletExit as e:
			print("Stopped handling responses")

