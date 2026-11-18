Option Explicit

' Silent background supervisor for Orion, launched at login by HKCU Run.
' Polls every few seconds and starts Orion only when it is genuinely absent.
' Uses Run rather than Exec so the watcher never holds a console handle or
' terminates a healthy assistant by mistake.

Dim shell, fso, project, pythonExe, command, stopFlag, logFile
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

project = fso.GetParentFolderName(WScript.ScriptFullName)
stopFlag = project & "\orion.stop"
logFile = project & "\orion_watch.log"

' A fresh login always starts Orion, even after a previous explicit Quit.
If fso.FileExists(stopFlag) Then fso.DeleteFile stopFlag, True

If fso.FileExists(project & "\.venv\Scripts\pythonw.exe") Then
    pythonExe = project & "\.venv\Scripts\pythonw.exe"
ElseIf fso.FileExists(project & "\venv\Scripts\pythonw.exe") Then
    pythonExe = project & "\venv\Scripts\pythonw.exe"
Else
    pythonExe = "pythonw.exe"
End If

command = """" & pythonExe & """ """ & project & "\orion.py"""

Function OrionRunning()
    Dim wmi, procs, proc
    OrionRunning = False
    On Error Resume Next
    Set wmi = GetObject("winmgmts:\\.\root\cimv2")
    Set procs = wmi.ExecQuery("Select CommandLine from Win32_Process Where Name = 'pythonw.exe'")
    For Each proc In procs
        If InStr(1, proc.CommandLine, "orion.py", vbTextCompare) > 0 Then
            OrionRunning = True
            Exit Function
        End If
    Next
    On Error GoTo 0
End Function

Sub WatchLog(message)
    On Error Resume Next
    Dim handle
    Set handle = fso.OpenTextFile(logFile, 8, True)
    handle.WriteLine Now & " " & message
    handle.Close
    On Error GoTo 0
End Sub

WatchLog "watchdog started"

Do While True
    If fso.FileExists(stopFlag) Then
        WatchLog "explicit stop requested"
        Exit Do
    End If

    If Not OrionRunning() Then
        WatchLog "starting Orion"
        shell.Run command, 0, False
        ' Give the process time to appear before checking again.
        WScript.Sleep 12000
    Else
        WScript.Sleep 4000
    End If
Loop

WatchLog "watchdog stopped"
