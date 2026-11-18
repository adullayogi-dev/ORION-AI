Option Explicit

' Background supervisor for Orion. Launched at login by HKCU Run.
' Starts the assistant with no console window and restarts it within a few
' seconds if it ever exits unexpectedly. A deliberate Sleep/Quit from the
' tray creates orion.stop, which makes this watcher exit instead.

Dim shell, fso, project, pythonExe, command, proc, stopFlag

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

project = fso.GetParentFolderName(WScript.ScriptFullName)
stopFlag = project & "\orion.stop"

' A fresh login must always start Orion, even if the previous session ended
' with an explicit Quit. Clear the stale marker once, here at startup.
If fso.FileExists(stopFlag) Then fso.DeleteFile stopFlag, True

If fso.FileExists(project & "\.venv\Scripts\pythonw.exe") Then
    pythonExe = project & "\.venv\Scripts\pythonw.exe"
ElseIf fso.FileExists(project & "\venv\Scripts\pythonw.exe") Then
    pythonExe = project & "\venv\Scripts\pythonw.exe"
Else
    pythonExe = "pythonw.exe"
End If

command = """" & pythonExe & """ """ & project & "\orion.py"""

Do While True
    If fso.FileExists(stopFlag) Then Exit Do

    On Error Resume Next
    Set proc = shell.Exec(command)
    If Err.Number <> 0 Then
        Err.Clear
    Else
        On Error GoTo 0
        Do While proc.Status = 0
            If fso.FileExists(stopFlag) Then
                On Error Resume Next
                proc.Terminate()
                On Error GoTo 0
                Exit Do
            End If
            WScript.Sleep 3000
        Loop
    End If
    On Error GoTo 0

    WScript.Sleep 3000
Loop
