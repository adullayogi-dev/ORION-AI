Option Explicit

' Starts Orion without a terminal window. The one-instance lock in orion.py
' prevents a duplicate if the assistant is already running.
' The project folder is derived from this script's own location, so moving the
' project (or OneDrive changing the Desktop path) cannot break silent start.
Dim shell, fso, project, pythonExe, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

project = fso.GetParentFolderName(WScript.ScriptFullName)

If fso.FileExists(project & "\.venv\Scripts\pythonw.exe") Then
    pythonExe = project & "\.venv\Scripts\pythonw.exe"
ElseIf fso.FileExists(project & "\venv\Scripts\pythonw.exe") Then
    pythonExe = project & "\venv\Scripts\pythonw.exe"
Else
    pythonExe = "pythonw.exe"
End If

command = """" & pythonExe & """ """ & project & "\orion.py"" --silent"
shell.Run command, 0, False
