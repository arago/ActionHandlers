#!/usr/bin/env python
import os
if os.environ.get('USER','') == 'vagrant':
    del os.link

import distutils.core

name = 'winrm-actionhandler'

distutils.core.setup(
	name = name,
	version = "2.3",
	author = "Marcus Klemm",
	author_email = "mklemm@arago.de",
	description = ("ActionHandler for Microsoft Windows"),
	license = "MIT",
	url = "http://www.arago.de",
	long_description="""\
Execute cmd.exe and powershell commands on remote
Windows hosts via the WinRM protocol.
""",
	classifiers=[
		"Development Status :: 5 - Production/Stable",
		"Topic :: Utilities",
		"License :: OSI Approved :: MIT License",
	],
	install_requires=['arago-pyactionhandler-winrm'],
	scripts=['bin/hiro-winrm-actionhandler.py'],
	data_files=[
		(
			'/opt/autopilot/conf/external_actionhandlers/',
			[
				'config/external_actionhandlers/winrm-actionhandler.conf',
				'config/external_actionhandlers/winrm-actionhandler-log.conf'
			]
		),
		(
			'/opt/autopilot/conf/external_actionhandlers/capabilities/',
			[
				'config/external_actionhandlers/capabilities/winrm-actionhandler.xml',
				'config/external_actionhandlers/capabilities/winrm-actionhandler.yaml'
			]
		),
		(
			'/etc/init.d/', ['etc/init.d/hiro-winrm-actionhandler']
		)
	]
)
