Set WshShell = CreateObject("WScript.Shell")
Set Fso = CreateObject("Scripting.FileSystemObject")

Root = Fso.GetParentFolderName(Fso.GetParentFolderName(WScript.ScriptFullName))
Launcher = Root & "\scripts\start-facai-agent-service.cmd"

WshShell.Run "cmd.exe /c """ & Launcher & """", 0, False
