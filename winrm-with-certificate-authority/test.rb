require 'winrm'
endpoint = 'http://ca1.adlab.loc:5985/wsman'
krb5_realm = 'ADLAB.LOC'
winrm = WinRM::WinRMWebService.new(endpoint, :kerberos, :realm => krb5_realm)
winrm.create_executor do |executor|
  executor.run_cmd('ipconfig /all') do |stdout, stderr|
    STDOUT.print stdout
    STDERR.print stderr
  end
end
