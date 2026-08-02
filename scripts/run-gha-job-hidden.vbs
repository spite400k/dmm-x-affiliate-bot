' Launch run-gha-job.ps1 with no console window (window style 0).
' Usage: wscript.exe run-gha-job-hidden.vbs <job-name>
Option Explicit

If WScript.Arguments.Count < 1 Then
  WScript.Quit 1
End If

Dim job, sh, fso, scriptDir, ps1, psExe, cmd, rc
job = WScript.Arguments(0)

Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
ps1 = scriptDir & "\run-gha-job.ps1"
psExe = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"

If Not fso.FileExists(ps1) Then
  WScript.Quit 2
End If

cmd = """" & psExe & """ -NoProfile -ExecutionPolicy Bypass -File """ & ps1 & """ -Job " & job

Set sh = CreateObject("WScript.Shell")
' 0 = hide window, True = wait for exit
rc = sh.Run(cmd, 0, True)
WScript.Quit rc
