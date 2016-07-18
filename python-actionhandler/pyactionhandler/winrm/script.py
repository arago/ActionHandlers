class Script(object):
	psWrapper="""\
$OutputEncoding=[console]::OutputEncoding=[console]::InputEncoding=[system.text.encoding]::GetEncoding([System.Text.Encoding]::Default.CodePage)
@'
mode con: cols={cols}
{script}
'@ | powershell - 2>&1 | %{{$e=@("psout","pserr")[[byte]($_.GetType().Name -eq "ErrorRecord")];return "<$e><![CDATA[$(([string]$_).TrimEnd(" `r`n"))]]></$e>"}} | write-host
exit $LastExitCode
"""
	cmdWrapper="""\
$t = [IO.Path]::GetTempFileName() | ren -NewName {{ $_ -replace 'tmp$', 'bat' }} -PassThru
@'
mode con: cols={cols}
{script}
'@ | out-file -encoding "OEM" $t
& cmd.exe /q /c $t 2>&1 | %{{$e=@("psout","pserr")[[byte]($_.GetType().Name -eq "ErrorRecord")];return "<$e><![CDATA[$(([string]$_).TrimEnd(" `r`n"))]]></$e>"}} | write-host
rm $t
exit $LastExitCode
"""
	def __init__(self, script, interpreter, cols):
		self.interpreter=interpreter
		if interpreter=='cmd': self.wrapper=self.cmdWrapper
		elif interpreter=='ps': self.wrapper=self.psWrapper
		else: pass
		self.script = script if script[-1] == "\n" else script + "\n"
		self.result=None
		self.cols = cols

	def run(self, Session):
		self.rs=Session.run_ps(
			self.wrapper.format(
				cols=self.cols,
				script=psesc(self.script)))

	def print_output(self):
		xml = "<root>\n" + self.rs.std_out.decode('cp850') + "</root>"
		#xml = xml.replace("\r\n", '')
		root = ET.fromstring(xml.encode('utf8'))
		nodes = root.findall("./*")
		for s in nodes:
			out =  s.text if s.text else ''
			if s.tag == 'pserr':
				sys.stderr.write(out)
			elif s.tag == 'psout':
				sys.stdout.write(out)
