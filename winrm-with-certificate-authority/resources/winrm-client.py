import sys
import argparse
import base64
from winrm.protocol import Protocol
import re
import xml.etree.ElementTree as ET
import codecs
import xmltodict
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

class myProtocol(Protocol):
    def get_command_output(self, shell_id, command_id):
        """
        Get the Output of the given shell and command
        @param string shell_id: The shell id on the remote machine.
         See #open_shell
        @param string command_id: The command id on the remote machine.
         See #run_command
        #@return [Hash] Returns a Hash with a key :exitcode and :data.
         Data is an Array of Hashes where the cooresponding key
        #   is either :stdout or :stderr.  The reason it is in an Array so so
         we can get the output in the order it ocurrs on
        #   the console.
        """
        stdout_buffer, stderr_buffer, stdall_buffer = [], [], []
        command_done = False
        while not command_done:
            stdall, stdout, stderr, return_code, command_done = \
                self._raw_get_command_output(shell_id, command_id)
            stdout_buffer.append(stdout)
            stderr_buffer.append(stderr)
            stdall_buffer.append(stdall)
        return ''.join(stdall_buffer), ''.join(stdout_buffer), ''.join(stderr_buffer), return_code

    def _raw_get_command_output(self, shell_id, command_id):
        rq = {'env:Envelope': self._get_soap_header(
            resource_uri='http://schemas.microsoft.com/wbem/wsman/1/windows/shell/cmd',  # NOQA
            action='http://schemas.microsoft.com/wbem/wsman/1/windows/shell/Receive',  # NOQA
            shell_id=shell_id)}

        stream = rq['env:Envelope'].setdefault(
            'env:Body', {}).setdefault('rsp:Receive', {})\
            .setdefault('rsp:DesiredStream', {})
        stream['@CommandId'] = command_id
        stream['#text'] = 'stderr stdout'

        rs = self.send_message(xmltodict.unparse(rq))
        root = ET.fromstring(rs)
        stream_nodes = [node for node in root.findall('.//*')
                        if node.tag.endswith('Stream')]
        stdout = stderr = stdall = ''
        return_code = -1
        for stream_node in stream_nodes:
            if stream_node.text:
                #print stream_node.attrib['Name'] + ":" + str(base64.b64decode(
                #        stream_node.text.encode('ascii')))
                if stream_node.attrib['Name'] == 'stdout':
                    stdout += str(base64.b64decode(
                        stream_node.text.encode('ascii')))
                elif stream_node.attrib['Name'] == 'stderr':
                    stderr += str(base64.b64decode(
                        stream_node.text.encode('ascii')))

        # We may need to get additional output if the stream has not finished.
        # The CommandState will change from Running to Done like so:
        # @example
        #   from...
        #   <rsp:CommandState CommandId="..." State="http://schemas.microsoft.com/wbem/wsman/1/windows/shell/CommandState/Running"/>  # NOQA
        #   to...
        #   <rsp:CommandState CommandId="..." State="http://schemas.microsoft.com/wbem/wsman/1/windows/shell/CommandState/Done">  # NOQA
        #     <rsp:ExitCode>0</rsp:ExitCode>
        #   </rsp:CommandState>
        command_done = len([node for node in root.findall('.//*')
                           if node.get('State', '').endswith(
                            'CommandState/Done')]) == 1
        if command_done:
            return_code = int(next(node for node in root.findall('.//*')
                                   if node.tag.endswith('ExitCode')).text)

        return stdall, stdout, stderr, return_code, command_done

    

p = myProtocol(
    endpoint="https://{hostname}:{port}/wsman".format(hostname=args.hostname, port=args.port),
    transport=args.transport,
    cert_pem=args.certificate.name,
    cert_key_pem=args.keyfile.name,
    server_cert_validation='ignore'
)

class Response(object):
    """Response from a remote command execution"""
    def __init__(self, args):
        self.std_all, self.std_out, self.std_err, self.status_code = args

    def __repr__(self):
        # TODO put tree dots at the end if out/err was truncated
        return '<Response code {0}, out "{1}", err "{2}", all "{3}">'.format(
            self.status_code, self.std_out, self.std_err, self.std_all)

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
        rs = run_cmd(p, "mode con: cols=1024 & powershell -encodedcommand %s" % (base64_script))
        if len(rs.std_err):
            # if there was an error message, clean it it up and make it human
            # readable
            rs.std_err = clean_error_msg(rs.std_err)
        return rs

def prep_powershell_script(script):
    # Terse, because we have a max length for the resulting command line and this thing is
    # still going to be base64-encoded. Twice
    return """\
$t = [IO.Path]::GetTempFileName()
[System.Text.Encoding]::Unicode.GetString([System.Convert]::FromBase64String("{script}")) >$t
gc $t | powershell - 2>&1 | %{{$e=@("psout","pserr")[[byte]($_.GetType().Name -eq "ErrorRecord")];return "<$e><![CDATA[$_]]></$e>"}}
rm $t
""".format(script=base64.b64encode(script.encode("utf_16_le")))
    
def prep_script(script):
    # Terse, because we have a max length for the resulting command line and this thing is
    # still going to be base64-encoded. Twice
    script = "@echo off\n" + script
    return """\
$t = [IO.Path]::GetTempFileName() | ren -NewName {{ $_ -replace 'tmp$', 'bat' }} -PassThru
[System.Text.Encoding]::Unicode.GetString([System.Convert]::FromBase64String("{script}")) | out-file -encoding "ASCII" $t
& cmd.exe /c $t 2>&1 | %{{$e=@("psout","pserr")[[byte]($_.GetType().Name -eq "ErrorRecord")];return "<$e><![CDATA[$_]]></$e>"}}
rm $t
""".format(script=base64.b64encode(script.encode("utf_16_le")))

def run_script(p, script):
    rs = run_ps(p, script)
    xml = "<root>\n" + rs.std_out.decode('cp850') + "</root>"
    root = ET.fromstring(xml.encode('utf8'))
    nodes = root.findall("./*")
    for s in nodes:
        if s.text:
            s.text = s.text.rstrip("\n ")
            if s.tag == 'pserr':
                print >>sys.stderr, s.text
            elif s.tag == 'psout':
                print >>sys.stdout, s.text

if args.interpreter == 'cmd':
    run_script(p, prep_script(args.script.read()))
elif args.interpreter == 'powershell':
    run_script(p, prep_powershell_script(args.script.read()))
