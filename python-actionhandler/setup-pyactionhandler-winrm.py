#!/usr/bin/env python
import os
if os.environ.get('USER','') == 'vagrant':
    del os.link

import distutils.core

name = 'arago-pyactionhandler-winrm'

distutils.core.setup(
	name = "arago-pyactionhandler-winrm",
	version = "2.0",
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
	packages=['arago.pyactionhandler.plugins.winrm',
			  'arago.pyactionhandler.plugins.winrm.auth.kerberos'
	],
	install_requires=['arago-pyactionhandler'],
	scripts=['bin/hiro-winrm-actionhandler.py'],
	data_files=[
		(
			'/opt/autopilot/conf/external_actionhandlers/',
			[
				'config/winrm-actionhandler.conf',
				'config/winrm-actionhandler-log.conf'
			]
		),
		(
			'/opt/autopilot/conf/external_actionhandlers/capabilities/',
			[
				'config/capabilities/winrm-actionhandler.xml',
				'config/capabilities/winrm-actionhandler.yaml'
			]
		),
		(
			'/etc/init.d/', ['etc/init.d/hiro-winrm-actionhandler']
		)
	]
)
