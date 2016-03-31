import sys
import argparse
import base64
from winrm.protocol import Protocol
import re
import xml.etree.ElementTree as ET
import codecs
sys.stdout = codecs.getwriter('utf8')(sys.stdout)

parser = argparse.ArgumentParser()

parser.add_argument("script", help="MANDATORY: path to a file contaning the commands", type=argparse.FileType('r'))
parser.add_argument("-H", "--hostname", help="MANDATORY: the hostname of the machine to execute the command on", required=True)
parser.add_argument("-p", "--port", help="the port WinRM is listening on on the target machine (default=5986)", type=int, default=5986)
parser.add_argument("-t", "--transport", help="the transport protocol in use (default=ssl), only ssl implemented by now", choices=['kerberos', 'ssl', 'plaintext'], default='ssl')
parser.add_argument("-c", "--certificate", help="MANDATORY: path to the file containing the client certificate", required=True, type=argparse.FileType('r'))
parser.add_argument("-k", "--keyfile", help="MANDATORY: path to the file containing the client certificate's private key", required=True, type=argparse.FileType('r'))
parser.add_argument("-i", "--interpreter", help="the command interpreter to use, either cmd or powershell (default)", choices=['cmd', 'powershell'], default='powershell')

args = parser.parse_args()

p = Protocol(
    endpoint="https://{hostname}:{port}/wsman".format(hostname=args.hostname, port=args.port),
    transport=args.transport,
    cert_pem=args.certificate.name,
    cert_key_pem=args.keyfile.name,
    server_cert_validation='ignore'
)

class Response(object):
    """Response from a remote command execution"""
    def __init__(self, args):
        self.std_out, self.std_err, self.status_code = args

    def __repr__(self):
        # TODO put tree dots at the end if out/err was truncated
        return '<Response code {0}, out "{1}", err "{2}">'.format(
            self.status_code, self.std_out[:20], self.std_err[:20])

def strip_namespace(xml):
        """strips any namespaces from an xml string"""
        try:
            p = re.compile("xmlns=*[\"\"][^\"\"]*[\"\"]")
            allmatches = p.finditer(xml)
            for match in allmatches:
                xml = xml.replace(match.group(), "")
            return xml
        except Exception as e:
            raise Exception(e)

def clean_error_msg(msg):
        """converts a Powershell CLIXML message to a more human readable string
        """

        # if the msg does not start with this, return it as is
        if msg.startswith("#< CLIXML\r\n"):
            # for proper xml, we need to remove the CLIXML part
            # (the first line)
            msg_xml = msg[11:]
            try:
                # remove the namespaces from the xml for easier processing
                msg_xml = strip_namespace(msg_xml)
                root = ET.fromstring(msg_xml)
                # the S node is the error message, find all S nodes
                nodes = root.findall("./S")
                new_msg = ""
                for s in nodes:
                    # append error msg string to result, also
                    # the hex chars represent CRLF so we replace with newline
                    new_msg += s.text.replace("_x000D__x000A_", "\n")
            except Exception as e:
                # if any of the above fails, the msg was not true xml
                # print a warning and return the orignal string
                print("Warning: there was a problem converting the Powershell"
                      " error message: %s" % (e))
            else:
                # if new_msg was populated, that's our error message
                # otherwise the original error message will be used
                if len(new_msg):
                    # remove leading and trailing whitespace while we are here
                    msg = new_msg.strip()
        return msg

def run_cmd(p, command, args=()):
        # TODO optimize perf. Do not call open/close shell every time
        shell_id = p.open_shell()
        command_id = p.run_command(shell_id, command, args)
        rs = Response(p.get_command_output(shell_id, command_id))
        p.cleanup_command(shell_id, command_id)
        p.close_shell(shell_id)
        return rs

def run_ps(p, script):
        """base64 encodes a Powershell script and executes the powershell
        encoded script command
        """

        # must use utf16 little endian on windows
        base64_script = base64.b64encode(script.encode("utf_16_le"))
        rs = run_cmd(p, "mode con: cols=32766 & powershell -encodedcommand %s" % (base64_script))
        if len(rs.std_err):
            # if there was an error message, clean it it up and make it human
            # readable
            rs.std_err = clean_error_msg(rs.std_err)
        return rs

def run_powershell(p, script):
    rs = run_ps(p, script)
    print >>sys.stdout, rs.std_out.decode('cp850')
    print >>sys.stderr, rs.std_err.decode('cp850')
    
def run_script(p, script):
    #print "Script:"
    #print script
    wrapper="""\
$tempfile = [IO.Path]::GetTempFileName() | Rename-Item -NewName {{ $_ -replace 'tmp$', 'bat' }} -PassThru
@"
@echo off

{script}
"@ -replace '\n', "`r`n" | out-file -encoding "ASCII" $tempfile

& cmd.exe /c $($tempfile.FullName) 2>&1 | where-object {{ if ($_ -is [System.Management.Automation.ErrorRecord]) {{ write-host "<pserr><![CDATA[$_]]></pserr>"; $false }} else {{ write-host "<psout><![CDATA[$_]]></psout>" }} }}
""".format(script=script)
    rs = run_ps(p, wrapper)
    xml = "<root>\n" + rs.std_out.decode('cp850') + "</root>"
    root = ET.fromstring(xml.encode('utf8'))
    nodes = root.findall("./*")
    for s in nodes:
        if s.tag == 'pserr':
            if s.text:
                print >>sys.stderr, s.text
            else:
                print >>sys.stderr, ""
        elif s.tag == 'psout':
            if s.text:
                print >>sys.stdout, s.text
            else:
                print >>sys.stdout, ""

if args.interpreter == 'cmd':
    run_script(p, args.script.read())
elif args.interpreter == 'powershell':
    run_powershell(p, args.script.read())
    
