' Start Lite Game Recorder v2.3 — no terminal window at all.
' Double-click this file. It runs the app with pyw.exe
' (Python's windowed launcher: no black console window).
' Use this if you already ran "Install Lite Game Recorder.bat" once
' (it installs the libraries). For a proper install with a Desktop
' icon, double-click "Install Lite Game Recorder.bat" instead.
Option Explicit
Dim shell, fso, folder, app
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
app = """" & folder & "\app.py"""
' 0 = hidden window, False = do not wait for the app to close
shell.Run "pyw.exe " & app, 0, False
