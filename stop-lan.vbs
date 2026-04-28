Set shell = CreateObject("WScript.Shell")
scriptPath = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\stop-lan.ps1"
shell.Run "powershell -ExecutionPolicy Bypass -File """ & scriptPath & """", 0, False
