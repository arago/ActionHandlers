# Roadmap

## Prio 1:

1. ~~Refactor the Python code into something one can show to an actual developer without giving him a heart attack.~~
2. ~~Decide on the final format of Powershell error messages in text mode~~

## Prio 2:

1. ~~Find a better way to return interleaved stdout/stderr channels than hand-rolled XML~~
   Thanks to some "features" of the WinRM protocol, this is currently the best approach. I'll revisit this topic
   when I've adapted the PSRP protocol.
2. Implement return codes

## In no specific order:

- Add an option to serialize Powershell objects to JSON for further processing in KIs (code name "object mode")
- Add documentation on how to use the Windows Active Directory PKI infrastructure instead of OpenSSL
- Investigate PKInit for authentication using AD domain accounts
- Split documentation into separate documents, keeping the Readme short
