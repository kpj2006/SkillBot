Set WshShell = CreateObject("WScript.Shell")
Dim botDir
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
Dim botDir
botDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.Run "cmd /c cd /d """ & botDir & """ && venv\Scripts\python.exe bot.py", 0, False