#!/usr/bin/env python
import os
if os.environ.get('USER','') == 'vagrant':
    del os.link

import distutils.core

name = 'arago-pyactionhandler-winrm'

distutils.core.setup(
	name = name,
	version = "2.1",
	author = "Marcus Klemm",
	author_email = "mklemm@arago.de",
	description = ("WinRM module for pyactionhandler"),
	license = "MIT",
	url = "http://www.arago.de",
	long_description="""\
Support for the Windows Remote Management protocol.
""",
	classifiers=[
		"Development Status :: 5 - Production/Stable",
		"Topic :: Utilities",
		"License :: OSI Approved :: MIT License",
	],
	packages=['arago.pyactionhandler.plugins.winrm',
			  'arago.pyactionhandler.plugins.winrm.auth.kerberos'
	],
	install_requires=['arago-pyactionhandler']
)
