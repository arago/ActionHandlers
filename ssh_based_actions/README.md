How to utilize SSH to run automation tasks on Linux/UNIX servers
================================================================

## Introduction
Most administrative tasks on Linux/UNIX servers boil down to:
* run a (single line) command
* run a scriplet
* copy some files

Here we want to show how this can be achieved with AutoPilot utilizing SSH.

## Environment 

### Assumption

* the server running AutoPilot engine can directly connect to SSHd on all target servers (for target user 'root' this includes that remote login for 'root' is allowed)
* the target servers are Linux servers (just for the sake of our sample configuration, can be easily extended to any UNIX)
* the SSHd on target servers is configured with `UseDNS no` or DNS reverse lookup is working properly (to prevent long timeouts during ssh login)

### Preparation

We have to make sure that AutoPilot Engine can _ssh_ to any target server as any users we want to run actions on the target. For the case of simplicity we assume that the target user will always be root.

This can be achieved like this:
* create pass-phrase free SSH key pair for AutoPilot engine. Log into AutoPilot engine server (as 'root') and do:
```
su - arago
ssh-keygen -t rsa -b 2048 -N "" -C "AutoPilot Automation Engine"
``` 
* this will produce two files
```
-rw------- 1 arago arago 1675 Feb 16 15:07 /opt/autopilot/.ssh/id_rsa
-rw-r--r-- 1 arago arago  409 Feb 16 15:07 /opt/autopilot/.ssh/id_rsa.pub
```
* add the content of `/opt/autopilot/.ssh/id_rsa.pub` to file `/root/.ssh/authorized_keys` on all target servers.
* in case you want to use a different target user than 'root' you have to add the pub key to `$HOME/.ssh/authorized_keys` with `$HOME` being the home directory of the target user

### More general setups

Since SSH is quite powerful you can achieve transparent access even if a direct access is not possible. E.g. you might need to _ssh_ to a hop server first and from there you can _ssh_ to the target servers. If the ssh pub-key is added to the `authorized_keys` of the hop-account you can still use the configurations described below if you add to `/opt/autopilot/.ssh/config` on AutoPilot Engine server something like this:
```
Host *.my.hidden.domain
 User root
 ProxyCommand ssh <hop-user>@<hop-server> /usr/bin/nc -w 90 %h %p
 ControlMaster auto
```

## Configuration of Generic Action Handler

Having the SSH connectivity in place as described above we can now configure the generic Action Handler to provide
* **ExecuteCommand**: execute command on remote host
* **RunScript**: run script on remote host
* **UploadFile**: copy files/directories (recursively) to remote server
* **DownloadFile**: copy files/directories (recursively) from remote server

for all Linux servers.

### aae.yaml

You have to add the following stanza to section `GenericHandler:` of file `/opt/autopilot/conf/aae.yaml`:

```yaml
- Applicability:
  - Priority: 100
    ModelFilter:
    - Var:
        Name: MachineClass
        Mode: string
        Value: "Linux"
  Capability:
  - Name: ExecuteCommand
    Description: execute command on remote host
    Command: ssh -o StrictHostKeyChecking=no -o BatchMode=yes -o LogLevel=quiet -i /opt/autopilot/.ssh/id_rsa ${User}@${Hostname} ${Command}
    Parameter:
    - Name: Command
      Description: command to execute
      Mandatory: true
    - Name: Hostname
      Description: host to execute command on
      Mandatory: true
    - Name: User
      Description: target user
      Mandatory: false
      Default: root
  - Name: RunScript
    Description: run script on remote host
    Interpreter: 'FNAME=`basename ${TEMPFILE}` ; scp -o StrictHostKeyChecking=no -o BatchMode=yes -o LogLevel=quiet -i /opt/autopilot/.ssh/id_rsa ${TEMPFILE} ${User}@${Hostname}: ; ssh -o StrictHostKeyChecking=no -o BatchMode=yes -o LogLevel=quiet -i /opt/autopilot/.ssh/id_rsa ${User}@${Hostname} ./$FNAME ; RESULT=$?; ssh -o StrictHostKeyChecking=no -o BatchMode=yes -o LogLevel=quiet -i /opt/autopilot/.ssh/id_rsa ${User}@${Hostname} rm -f ${FNAME}; exit $RESULT'
    Command: ${Command}
    Parameter:
    - Name: Command
      Description: scriptlet to execute
      Mandatory: true
    - Name: Hostname
      Description: host to execute command on
      Mandatory: true
    - Name: User
      Description: target user
      Mandatory: false
      Default: root
  - Name: UploadFile
    Description: copy files/directories (recursively) to remote server
    Command: scp -r -o StrictHostKeyChecking=no -o BatchMode=yes -i /opt/autopilot/.ssh/id_rsa ${Source} ${User}@${Hostname}:${Target}
    Parameter:
    - Name: Source
      Description: could be single file/directory or a list
      Mandatory: true
    - Name: Hostname
      Description: host to copy to
      Mandatory: true
    - Name: User
      Description: target user
      Default: root
    - Name: Target
      Description: target dir/file to copy to
      Default: ""
  - Name: DownloadFile
    Description: copy files/directories (recursively) from remote server
    Command: if [ -n "${CreateTarget}" ]; then mkdir -p ${Target}; fi; scp -r -o StrictHostKeyChecking=no -o BatchMode=yes -i /opt/autopilot/.ssh/id_rsa ${User}@${Hostname}:${Source} ${Target}
    Parameter:
    - Name: Source
      Description: no list supported. but wildcards can be used
      Mandatory: true
    - Name: Hostname
      Description: host to copy to
      Mandatory: true
    - Name: User
      Description: target user
      Default: root
    - Name: Target
      Description: target dir/file to copy to
      Mandatory: true
    - Name: CreateTarget
      Description: will create target directory if non-empty value is set
      Default: ""
```

## Sample usage in KI (Knowledge Item)

We don't show full KIs here. Just the `<Action>` element you have to produce. Using KI Editor you would not write the `<Action>` element directly but after doing it once with the UI it will be quite obvious how to create the corresponding element in KI Editor.

In the examples all the `Parameter` settings contain hard coded values. In real life most of those parameters will contain placeholder variables (`${..}` constructs) that will be expanded from KI context variables.

### ExecuteCommand

as 'root' relying on default user setting:
```xml
<Action Capability="ExecuteCommand" Timeout="60">
    <Parameter Name="Command">ls -l /</Parameter>
    <Parameter Name="Hostname">my.host.com</Parameter>
</Action>
```

as 'root' specifying user explicitly:
```xml
<Action Capability="ExecuteCommand" Timeout="60">
    <Parameter Name="Command">ls -l /</Parameter>
    <Parameter Name="Hostname">my.host.com</Parameter>
    <Parameter Name="User">root</Parameter>    
</Action>
```

### RunScript

as 'root' specifying user explicitly:

```xml
<Action Capability="RunScript" Timeout="30">
        <Parameter Name="Hostname">server1.my.domain</Parameter>
        <Parameter Name="User">root</Parameter>    
        <Parameter Name="Command"><![CDATA[#!/usr/bin/perl -w
#  - get uid of user 'oracle'
$uid = getpwnam('oracle');
print $uid;
]]></Parameter>
    </Action>
```

you can achieve the same without `<Parameter Name="User">root</Parameter>` since 'root' is default.

### UploadFile

as 'root' relying on default user setting:
```xml
<Action Capability="UploadFile" Timeout="30"> 
      <Parameter Name="Hostname">my.host.com</Parameter> 
      <Parameter Name="Source">/templates/etc_motd</Parameter> 
      <Parameter Name="Target">/etc/motd</Parameter> 
</Action> 
```

### DownloadFile
as 'root' specifying user explicitly:
```xml
<Action Capability="DownloadFile" Timeout="60" > 
   <Parameter Name="Hostname">my.host.com</Parameter> 
   <Parameter Name="User">root</Parameter> 
   <Parameter Name="Source">/etc/passwd</Parameter> 
   <Parameter Name="Target">/gathered_data/my.host.com</Parameter> 
   <Parameter Name="CreateTarget">1</Parameter> 
</Action> 
```
