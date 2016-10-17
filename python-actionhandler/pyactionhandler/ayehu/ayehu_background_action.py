import gevent
from pyactionhandler.ayehu.exceptions import IssueUpdateError
from pygraphit import GraphitNode
from pygraphit.exceptions import GraphitError, WSO2TokenRenewalError
from xml.etree.ElementTree import Element, SubElement, tostring
from pyactionhandler.ayehu.ayehu_action import AyehuAction

class AyehuBackgroundAction(AyehuAction):
	def __init__(self, num, node, zmq_info, timeout, parameters,
				 zeep_transport, redis, ayehu_config, pmp_config,
				 rest_api, graphit_session, deployment_timeout):
		super(AyehuBackgroundAction, self).__init__(
			num, node, zmq_info, timeout, parameters,
			zeep_transport, redis, ayehu_config, pmp_config,
			rest_api)
		self.graphit_session=graphit_session
		self.deployment_timeout=deployment_timeout

	def __call__(self):
		# pubsub object must be greenlet-local
		self.pubsub=self.redis.pubsub(ignore_subscribe_messages=True)

		# process action
		self.create_rest_resource()
		self.open_incident()
		self.return_cmdid()
		gevent.spawn(self.wait_for_background_action)

	def wait_for_background_action(self):
		try:
			with gevent.Timeout(self.timeout):
				self.logger.info(
					"[{anum}] Waiting {to} seconds for results".format(
						anum=self.num, to=self.timeout))
				self.wait_for_rest_callback()
				self.logger.info(
					"[{anum}] Background execution was terminated, updating Issue '{iid}'".format(
						anum=self.num,
						iid=self.parameters['IID']))
				self.update_issue()
		except gevent.Timeout:
			if callable(getattr(self, '__timeout__', None)):
				self.__timeout__(self.timeout)
			self.logger.info(
				"[{anum}] Background execution timed out.".format(
					anum=self.num))

	def create_xml(self):
		xmlroot=Element(
			'Issue',
			{"xmlns":"https://graphit.co/schemas/v2/IssueSchema"})
		issue_vars={
			self.parameters['RC']:str(self.system_rc),
			self.parameters['Output']:self.output,
			self.parameters['Error']:self.error_output
		}
		for name, value in issue_vars.items():
			SubElement(
				SubElement(xmlroot, name),
				'Content', {
					'Key':self.cmdid,
					'Value':value})
		return tostring(xmlroot,encoding="unicode")

	def update_issue(self):
		node = GraphitNode(
			self.graphit_session,
			self.parameters['IID'],
			"ogit/Automation/AutomationIssue",
			{
				"ogit/Automation/deployStatus":None,
				"ogit/Automation/isDeployed":None,
				"ogit/Automation/issueFormalRepresentation":self.create_xml()
			})
		try:
			node.push()
			with gevent.Timeout(self.deployment_timeout):
				while 'ogit/Automation/isDeployed' not in node.nodeBody or node.nodeBody['ogit/Automation/isDeployed'] is None: # WORKAROUND, mit Stefan klaeren!!!
					node.pull()
					gevent.sleep(1)
				if not node.nodeBody['ogit/Automation/isDeployed']:
					raise IssueUpdateError(node.nodeBody['ogit/Automation/deployStatus'])
		except GraphitError as e:
			self.logger.debug(
				"[{anum}] Error writing to GraphIT: {msg}".format(anum=self.num, msg=e.message))
		except WSO2TokenRenewalError as e:
			self.logger.critical("[{anum}] WSO2 Error: {err}".format(
				err=e))
		except gevent.Timeout:
			self.logger.error("[{anum}] Could not update Issue {iid} within {to} seconds!".format(
				anum=self.num,
				iid=self.parameters['IID'],
				to=self.deployment_timeout))
		except IssueUpdateError as e:
			self.logger.error("[{anum}] Error updating Issue {iid}: {e}".format(anum=self.num,e=e))

	def return_cmdid(self):
		self.output=self.cmdid
		self.system_rc=0
		self.success=True
