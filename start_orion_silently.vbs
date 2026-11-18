Option Explicit

' Starts Orion without a terminal window. The one-instance lock in orion.py
' prevents a duplicate if the assistant is already running.
' Resolves the virtual environment automatically: newer installs use "venv",
' older ones used ".venv".
Dim shell, fso, project, pythonExe, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

project = "C:\Users\adull\OneDrive\Desktop\ORION-AI"

If fso.FileExists(project & "\.venv\Scripts\pythonw.exe") Then
    pythonExe = project & "\.venv\Scripts\pythonw.exe"
ElseIf fso.FileExists(project & "\venv\Scripts\pythonw.exe") Then
    pythonExe = project & "\venv\Scripts\pythonw.exe"
Else
    pythonExe = "pythonw.exe"
End If

command = """" & pythonExe & """ """ & project & "\orion.py" & """"
shell.Run command, 0, False
