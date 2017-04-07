#!/usr/bin/env python
import os
if os.environ.get('USER','') == 'vagrant':
    del os.link

import distutils.core

distutils.core.setup(
	name = "arago-pyconnectit-common-rest-plugins-base",
	version = "2.1",
	author = "Marcus Klemm",
	author_email = "mklemm@arago.de",
	description = ("pyconnectit REST interface base plugins"),
	license = "MIT",
	url = "http://www.arago.de",
	long_description="pyconnectit REST interface base plugins",
	classifiers=[
		"Development Status :: 5 - Production/Stable",
		"Topic :: Utilities",
		"License :: OSI Approved :: MIT License",
	],
	packages=['arago.pyconnectit.common.rest.plugins.auth.basic',
			  'arago.pyconnectit.common.rest.plugins.json_translator',
			  'arago.pyconnectit.common.rest.plugins.require_json',
			  'arago.pyconnectit.common.rest.plugins.restrict_environment',
			  'arago.pyconnectit.common.rest.plugins.rest_logger']
)
