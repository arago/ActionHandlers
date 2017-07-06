#!/usr/bin/env python
"""netcool-control.py: Enable or disable event forwarding

Usage:
  netcool-control [options] (enable | disable) <environment>

Options:
  --level=LEVEL   loglevel [default: WARNING]
  --config=FILE   Path to config file [default: /opt/autopilot/connectit/conf/connectit-netcool-adapter-environments.conf]
"""
import zeep, logging, os, sys, requests, re

from docopt import docopt, printable_usage
from configparser import ConfigParser
from arago.common.logging.logger import Logger
from arago.pyconnectit.protocols.soap.plugins.soap_logger import SOAPLogger

args = docopt(__doc__, version='netcool-control 0.1')

environments_config_file = args['--config']
share_dir = os.path.join(os.getenv('PYTHON_DATADIR'), 'connectit-netcool-adapter')


# Read config file
environments_config=ConfigParser()
environments_config.read(environments_config_file)

# Setup logging
logging.setLoggerClass(Logger)
logger = logging.getLogger('root')
logger.setLevel(args['--level'])
stream_handler = logging.StreamHandler()
stream_handler.setLevel(args['--level'])
stream_formatter = logging.Formatter("[%(levelname)s] %(message)s")
stream_handler.setFormatter(stream_formatter)
logger.addHandler(stream_handler)


pattern = re.compile("^(?P<loc>[A-Z]+)_(?P<env>[A-Z]+)$")
parsed_args = pattern.match(args['<environment>'])
if not parsed_args:
	print(printable_usage(__doc__) + "\n", file=sys.stderr)
	logger.error("'{arg}' is not a valid value for <environment>!".format(arg=args['<environment>']))
	sys.exit(5)
target=parsed_args.groupdict()

def setup_soapclient(env, prefix, verify=False):
	plugins=[]
	if logger.getEffectiveLevel() <= logger.TRACE:
		plugins.append(SOAPLogger())
	session = requests.Session()
	session.verify = verify
	try:
		session.auth = requests.auth.HTTPBasicAuth(
			environments_config[env][prefix + 'username'],
			environments_config[env][prefix + 'password'])
	except KeyError:
		logger.warning("No authentication data given for {env} using {wsdl}".format(
				env=env,
				wsdl=os.path.basename(
					environments_config[env][prefix + 'wsdl_file'])))
	finally:
		soap_client = zeep.Client(
			'file://' + environments_config[env][prefix + 'wsdl_file'],
			transport=zeep.Transport(session=session),
			plugins=plugins)
		setattr(soap_client, prefix + "service", soap_client.create_service(
			environments_config[env][prefix + 'service_binding'],
			environments_config[env][prefix + 'endpoint']))
		logger.info(
			"Setting up SOAP client for {env} using {wsdl}".format(
				env=env,
				wsdl=os.path.basename(
					environments_config[env][prefix + 'wsdl_file'])))
		return soap_client
try:
	x = setup_soapclient(target['env'], 'netcool_')
except KeyError:
	logger.error("Environment {env} not found in {conf}".format(env=target['env'], conf=environments_config_file))
	sys.exit(10)

response = x.netcool_service.runPolicy(
	"disable_enable_hiro",
	{
		'desc': "stopStartHiroInterface",
		'format': "String",
		'label': "HIRO2NETCOOL",
		'name': "HIRO2NETCOOL",
		'value': "{target},{operation}".format(target=args['<environment>'], operation="enable" if args['enable'] else "disable")
	},
	True
)
results = {item['name']:item['value']
					   for item
					   in response}

if results['NetcoolProcessingError'] == 'true' or results['ProcessLimitExceeded'] == 'true' or 'Message' in results:
	logger.error("SOAP call failed: {cause}".format(cause=results['Message'] if 'Message' in results else "Unknown error"))
	sys.exit(15)
sys.exit(0)
