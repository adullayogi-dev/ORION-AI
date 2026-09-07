Option Explicit

' Starts Orion without a terminal window. The one-instance lock in orion.py
' prevents a duplicate if the assistant is already running.
Dim shell, project, command
Set shell = CreateObject("WScript.Shell")
project = "C:\Users\adull\OneDrive\Desktop\ORION-AI"
command = """" & project & "\.venv\Scripts\pythonw.exe" & """ """ & project & "\orion.py" & """"
shell.Run command, 0, False
