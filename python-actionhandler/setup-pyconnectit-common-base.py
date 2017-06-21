#!/usr/bin/env python
import os
if os.environ.get('USER','') == 'vagrant':
    del os.link

import distutils.core

distutils.core.setup(
	name = "arago-pyconnectit-common-base",
	version = "2.4",
	author = "Marcus Klemm",
	author_email = "mklemm@arago.de",
	description = ("Common functions and classes for pyconnectit"),
	license = "MIT",
	url = "http://www.arago.de",
	long_description="Common functions and classes for pyconnectit",
	classifiers=[
		"Development Status :: 5 - Production/Stable",
		"Topic :: Utilities",
		"License :: OSI Approved :: MIT License",
	],
	packages=['arago.pyconnectit.common.delta_store',
			  'arago.pyconnectit.common.lmdb_queue'
	]
)
