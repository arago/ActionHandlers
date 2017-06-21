#!/usr/bin/env python
import os
if os.environ.get('USER','') == 'vagrant':
    del os.link

import distutils.core

distutils.core.setup(
	name = "arago-pyconnectit-common-rest-plugins-storedeltas",
	version = "2.3",
	author = "Marcus Klemm",
	author_email = "mklemm@arago.de",
	description = ("Middleware to store SDF deltas"),
	license = "MIT",
	url = "http://www.arago.de",
	long_description="Middleware to store SDF deltas",
	classifiers=[
		"Development Status :: 5 - Production/Stable",
		"Topic :: Utilities",
		"License :: OSI Approved :: MIT License",
	],
	packages=['arago.pyconnectit.common.rest.plugins.store_deltas']
)
