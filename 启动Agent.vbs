' 法采新媒体运营Agent 启动器（无黑框）
Set objShell = CreateObject("WScript.Shell")
strPath = "D:\facai-agent-local"

' 检查是否已经在运行
Set objWMI = GetObject("winmgmts:\\.\root\cimv2")
Set colProcesses = objWMI.ExecQuery("SELECT * FROM Win32_Process WHERE CommandLine LIKE '%facai-agent-local%main.py%'")
If colProcesses.Count > 0 Then
    MsgBox "服务已在运行！" & vbCrLf & "打开浏览器访问：http://localhost:8001/app", 64, "法采新媒体运营Agent"
    objShell.Run "cmd /c start http://localhost:8001/app", 0, False
    WScript.Quit
End If

' 启动服务（隐藏窗口）
objShell.Run "cmd /c cd /d " & strPath & " && python main.py", 0, False

' 等待2秒后打开浏览器
WScript.Sleep 2500
objShell.Run "cmd /c start http://localhost:8001/app", 0, False
