Title:   A simple WMI-based ActionHandler for Windows nodes
Author:  Marcus Klemm
Date:    December 7, 2015  


# Simple ActionHandler to execute commands on Windows machines using WMI

This guide shows how to install everything from scratch. 

## Install the required packages

### Download and install the RepoForge repository:

The version of python-crypto in the standard CentOS 6 repository is too old, so I'm using the one from RepoForge:

```bash
wget http://pkgs.repoforge.org/rpmforge-release/rpmforge-release-0.5.3-1.el6.rf.x86_64.rpm
yum localinstall rpmforge-release-0.5.3-1.el6.rf.x86_64.rpm
```

### Install the packages:

```bash
yum install --enablerepo=rpmforge-extras` python-crypto python-pyasn1 unix2dos dos2unix
```

## Download and install the impacket python library:

### Checkout the latest version:

```bash
git clone https://github.com/CoreSecurity/impacket.git
```

### Patch the wmiexec.py script to support the "-quiet" option and remove the banner as well as the interactive warning:

```bash
patch -i wmiexec.patch impacket/examples/wmiexec.py
```

### Build and install:

```bash
cd impacket
python setup.py install
```

## Add the ActionHandler definition

Add the following definition to your /opt/autopilot/conf/aae.yaml file:

```yaml
# WMI based remote execution
- Applicability:
    Priority: 70
    ModelFilter:
      AttributeFilter:
        Name: NodeType
        Mode: string
        Value: Machine
      AttributeFilter:
        Name: MachineClass
        Mode: string
        Value: Windows
  Capability:
  - Name: ExecuteCommand
    Description: "execute command on remote host"
	# Explanation:
	#
	# Command is taken from the KI element "Action". An additional command
	# "exit" is appended, so that the remote shell will get terminated
	# after command execution. The resulting command string is written to
	# TEMPFILE.
	#
	# The interpreter line then pipes the command string through unix2dos
	# in order to replace the unix-style linefeeds with their DOS
	# counterpart. This is necessary for cmd.exe to recognize them as
	# "Return".
	#
	# The command is then fed into wmiexec, which takes care of creating a
	# new shell process on the target machine as well as fetching the
	# output via the SMB protocol.
	#
	# The output is then converted back to unix-style linefeeds and UTF8
	# encoding (cmd.exe uses CP437 or CP850 depending on the system
	# language).
	#
	# Last step is to strip an escape sequence that is introduced due to a
	# bug in some python library as well as the leading cmd.exe prompts
	# from the output.
    Interpreter: <${TEMPFILE} unix2dos | wmiexec.py -quiet ${User}:${Password}@${Hostname} 2>/dev/null | dos2unix | iconv -f CP850 -t UTF-8 | sed 's|\x1b\[[?]1034h||g' | sed 's|^[A-Z]:\\[^>]*>||g'
    Command: |
      ${Command}
      exit
    Parameter:
    - Name: Command
      Description: "command to execute"
      Mandatory: true
    - Name: Hostname
      Description: "host to execute command on"
      Mandatory: true
    - Name: User
      Description: "target user"
      Default: vagrant
    - Name: Password
      Description: "target user's password"
      Default: vagrant
```

Replace User and Password according to the environment. You can also reference attributes from MARS, please see the section [Dynamic values](https://autopilot.co/docs/5.2.1/html/content/5.2-connectors-generic-actionhandler.html#dynamic_values) from the Generic ActionHandler documentation.

Impacket's WMI implementation  seems to support Kerberos authentification as well, but I have not tried it, yet.

##Executables 

If you are looking for the mentioned 3rd party executables and files required to set this up, please contact us at autopilot-support@arago.de .
