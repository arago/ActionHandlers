"""Generic linux daemon base class for python 3.x."""

import sys, os, time, atexit, signal

class daemon:
	"""A generic daemon class.

	Usage: subclass the daemon class and override the run() method."""

	def __init__(self, pidfile, debug=False, nofork=False, debuglevel='DEBUG', uid='arago', gid='arago'):
		self.pidfile = pidfile
		self.debug=debug
		self.nofork=nofork
		self.debuglevel=debuglevel
		self.uid=uid
		self.gid=gid

	def daemonize(self):
		"""Deamonize class. UNIX double fork mechanism."""

		try:
			pid = os.fork()
			if pid > 0:
				# exit first parent
				sys.exit(0)
		except OSError as err:
			sys.stderr.write('fork #1 failed: {0}\n'.format(err))
			sys.exit(1)

		# decouple from parent environment
		os.chdir('/')
		os.setsid()
		os.umask(0)

		# do second fork
		try:
			pid = os.fork()
			if pid > 0:

				# exit from second parent
				sys.exit(0)
		except OSError as err:
			sys.stderr.write('fork #2 failed: {0}\n'.format(err))
			sys.exit(1)

		# redirect standard file descriptors
		sys.stdout.flush()
		sys.stderr.flush()
		si = open(os.devnull, 'r')
		so = open(os.devnull, 'a+')
		se = open(os.devnull, 'a+')

		if not self.debug and not self.nofork:
			os.dup2(si.fileno(), sys.stdin.fileno())
			os.dup2(so.fileno(), sys.stdout.fileno())
			os.dup2(se.fileno(), sys.stderr.fileno())

		# write pidfile
		#atexit.register(self.delpid)

		pid = str(os.getpid())
		with open(self.pidfile,'w+') as f:
			f.write(pid + '\n')

	@staticmethod
	def drop_privileges(uid_name='nobody', gid_name='nogroup'):

		import os, pwd, grp

		starting_uid = os.getuid()
		starting_gid = os.getgid()

		starting_uid_name = pwd.getpwuid(starting_uid)[0]

		# logger.info('drop_privileges: started as %s/%s' % \
		# 		 (pwd.getpwuid(starting_uid)[0],
		# 		  grp.getgrgid(starting_gid)[0]))

		if os.getuid() != 0:
			# We're not root so, like, whatever dude
			# logger.info("drop_privileges: already running as '%s'" % starting_uid_name)
			return

		# If we started as root, drop privs and become the specified user/group
		if starting_uid == 0:

			# Get the uid/gid from the name
			running_uid = pwd.getpwnam(uid_name)[2]
			running_gid = grp.getgrnam(gid_name)[2]

			# Try setting the new uid/gid
			try:
				os.setgid(running_gid)
			except OSError as e:
				pass
				# logger.error('Could not set effective group id: %s' % e)

			try:
				os.setuid(running_uid)
			except OSError as e:
				pass
				# logger.error('Could not set effective user id: %s' % e)

			# Ensure a very convervative umask
			new_umask = 77
			old_umask = os.umask(new_umask)
			# logger.info('drop_privileges: Old umask: %s, new umask: %s' % \
			# 		 (oct(old_umask), oct(new_umask)))

		final_uid = os.getuid()
		final_gid = os.getgid()
		# logger.info('drop_privileges: running as %s/%s' % \
		# 		 (pwd.getpwuid(final_uid)[0],
		# 		  grp.getgrgid(final_gid)[0]))

	def delpid(self):
		os.remove(self.pidfile)

	def start(self):
		"""Start the daemon."""

		# Check for a pidfile to see if the daemon already runs
		try:
			with open(self.pidfile,'r') as pf:

				pid = int(pf.read().strip())
		except IOError:
			pid = None

		if pid:
			message = "pidfile {0} already exist. " + \
					"Daemon already running?\n"
			sys.stderr.write(message.format(self.pidfile))
			sys.exit(1)

		# Start the daemon
		if not self.debug and not self.nofork:
			self.daemonize()
		self.drop_privileges(uid_name=self.uid, gid_name=self.gid)
		self.run()

	def stop(self):
		"""Stop the daemon."""

		# Get the pid from the pidfile
		try:
			with open(self.pidfile,'r') as pf:
				pid = int(pf.read().strip())
		except IOError:
			pid = None

		if not pid:
			message = "pidfile {0} does not exist. " + \
					"Daemon not running?\n"
			sys.stderr.write(message.format(self.pidfile))
			return # not an error in a restart

		# Try killing the daemon process
		try:
			while 1:
				os.kill(pid, signal.SIGTERM)
				time.sleep(0.1)
		except OSError as err:
			e = str(err.args)
			if e.find("No such process") > 0:
				if os.path.exists(self.pidfile):
					os.remove(self.pidfile)
			else:
				print (str(err.args))
				sys.exit(1)

	def restart(self):
		"""Restart the daemon."""
		self.stop()
		self.start()

	def run(self):
		"""You should override this method when you subclass Daemon.

		It will be called after the process has been daemonized by
		start() or restart()."""
