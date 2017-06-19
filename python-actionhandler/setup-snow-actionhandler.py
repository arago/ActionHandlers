#!/usr/bin/env python
import os
if os.environ.get('USER','') == 'vagrant':
    del os.link

import distutils.core

name = 'snow-actionhandler'

distutils.core.setup(
	name = name,
	version = "0.4.1",
	author = "Marcus Klemm",
	author_email = "mklemm@arago.de",
	description = ("ActionHandler for ServiceNow"),
	license = "MIT",
	url = "http://www.arago.de",
	long_description="""\
Create incident tickets in ServiceNow
""",
	classifiers=[
		"Development Status :: 5 - Production/Stable",
		"Topic :: Utilities",
		"License :: OSI Approved :: MIT License",
	],
	install_requires=['arago-pyactionhandler', "zeep"],
	packages=['arago.pyactionhandler.plugins.issue_api'],
	scripts=['bin/hiro-snow-actionhandler.py'],
	data_files=[
		(
			'/opt/autopilot/conf/external_actionhandlers/',
			[
				'config/external_actionhandlers/snow-actionhandler.conf',
				'config/external_actionhandlers/snow-actionhandler-environments.conf',
				'config/external_actionhandlers/snow-actionhandler-log.conf',
				'config/external_actionhandlers/snow-actionhandler-snow.wsdl'
			]
		),
		(
			'/opt/autopilot/conf/external_actionhandlers/capabilities/',
			[
				'config/external_actionhandlers/capabilities/snow-actionhandler.yaml'
			]
		),
		(
			'/etc/init.d/', ['etc/init.d/hiro-snow-actionhandler']
		)
	]
)
