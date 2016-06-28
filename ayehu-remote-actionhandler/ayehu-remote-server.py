#!/usr/bin/env python

import ayahu_actionhandler_rest as rest
import redis
import falcon
import urlparse
import ConfigParser

server_config = ConfigParser.ConfigParser()
server_config.read('/opt/autopilot/conf/ayehu-rest.conf')

api = application = falcon.API()
baseurl=server_config.get('default', 'CallbackBaseURL')
basepath=urlparse.urlparse(baseurl).path

redis = redis.StrictRedis(
	host=server_config.get('default', 'RedisHost'),
	port=server_config.get('default', 'RedisPort'),
	db=server_config.get('default', 'RedisDB'))
collection = rest.CommandCollection(redis, baseurl)
command = rest.Command(collection)
props = rest.Property(command)
stdout = rest.Output(command, 'stdout')
stderr = rest.Output(command, 'stderr')
cmdexit = rest.Exit(command)

api.add_route(
	'{basepath}/commands'.format(basepath=basepath),
	collection)
api.add_route(
	'{basepath}/commands/{{id}}'.format(basepath=basepath),
	command)
api.add_route(
	'{basepath}/commands/{{id}}/exit'.format(basepath=basepath),
	cmdexit)
api.add_route(
	'{basepath}/commands/{{id}}/property/{{name}}'.format(
		basepath=basepath),
	props)
api.add_route(
	'{basepath}/commands/{{id}}/output/stdout'.format(basepath=basepath),
	stdout)
api.add_route(
	'{basepath}/commands/{{id}}/output/stderr'.format(basepath=basepath),
	stderr)
