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

* the server running AutoPilot engine can directly connect to SSHd on all target servers (for target user 'root' this includes that remote loging for 'root' is allowed)
* the target servers are Linux servers (just for the sake of our sample configuration, can be easily extened to any UNIX)

### Preparation

We have to make sure that AutoPilot Engine can _ssh_ to any target server as any users we want to run actions on the target. For the case of simplicity we assume that the target user will alway be root.

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
* add the content of `/opt/autopilot/.ssh/id_rsa.pub` to file `/root/.ssh/authorized_keys' on all target servers.
* in case you want to use a different target user you have to add the pub key to `$HOME/.ssh/authorized_keys` with `$HOME` being the home directory of the target user

## Configuration of Generic Action Handler

Having the SSH connectivity in place as described above we can now configure the generic Action Handler such that it will provide
* ExecuteCommand: execute command on remote host
* RunScript: run script on remote host
* UploadFile: copy files/directories (recursively) to remote server
* DownloadFile: copy files/directories (recursively) from remote server
for all Linux servers.

### aae.yaml

You have to add the following stanza to section `GenericHandler:` of file `/opt/autopilot/conf/aae.yaml`:

```
TODO
```

## Sample usage in KI

### ExecuteCommand

### RunScript

### UploadFile

### DownloadFile
