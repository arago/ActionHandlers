#!/usr/bin/env python
import os
if os.environ.get('USER','') == 'vagrant':
    del os.link

import distutils.core

distutils.core.setup(
	name = "arago-pyconnectit-connectors-netcool",
	version = "2.3",
	author = "Marcus Klemm",
	author_email = "mklemm@arago.de",
	description = ("pyconnectit handlers for Netcool"),
	license = "MIT",
	url = "http://www.arago.de",
	long_description="pyconnectit handlers for Netcool",
	classifiers=[
		"Development Status :: 5 - Production/Stable",
		"Topic :: Utilities",
		"License :: OSI Approved :: MIT License",
	],
	packages=['arago.pyconnectit.connectors.netcool.handlers.sync_netcool_status']
)
