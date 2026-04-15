[Version]
Class=IEXPRESS
SEDVersion=3

[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=0
HideExtractAnimation=0
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=%InstallPrompt%
DisplayLicense=%DisplayLicense%
FinishMessage=%FinishMessage%
TargetName=%TargetName%
FriendlyName=%FriendlyName%
AppLaunched=%AppLaunched%
PostInstallCmd=%PostInstallCmd%
AdminQuietInstCmd=%AdminQuietInstCmd%
UserQuietInstCmd=%UserQuietInstCmd%
FILE0=%FILE0%
FILE1=%FILE1%
SourceFiles=SourceFiles

[SourceFiles]
SourceFiles0=c:\Users\gilad\Documents\anti\shuk15\dist
SourceFiles1=c:\Users\gilad\Documents\anti\shuk15\installer

[SourceFiles0]
%FILE0%=

[SourceFiles1]
%FILE1%=

[Strings]
InstallPrompt=
DisplayLicense=
FinishMessage=FPI Trading Compare was installed successfully.
TargetName=c:\Users\gilad\Documents\anti\shuk15\dist\FPITradingCompare-Setup.exe
FriendlyName=FPI Trading Compare Setup
AppLaunched=install.cmd
PostInstallCmd=<None>
AdminQuietInstCmd=install.cmd
UserQuietInstCmd=install.cmd
FILE0=FPITradingCompare.exe
FILE1=install.cmd