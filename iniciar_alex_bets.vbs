Set objShell = CreateObject("WScript.Shell")
strRuta = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
objShell.CurrentDirectory = strRuta

' El "0" oculta la ventana; "False" hace que no se espere a que termine.
objShell.Run "cmd /c python telegram_listener.py > listener.log 2>&1", 0, False
objShell.Run "cmd /c python -m streamlit run app.py > app.log 2>&1", 0, False
