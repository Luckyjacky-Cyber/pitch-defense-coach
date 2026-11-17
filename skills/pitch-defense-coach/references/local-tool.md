# 本机部署

Python 3.10+。基本网页、计时和文字输入只依赖标准库；Chrome/Edge等现代浏览器支持摄像头。本模板没有远端AI后端，当前使用Skill的AI负责出题和复盘。

将 `<skill>` 替换为本Skill目录，`<app>` 为新建的项目工具目录。路径含空格请加引号。

```text
python <skill>/scripts/bootstrap.py --target <app>
python <app>/server.py --port 8769
```

打开 `http://127.0.0.1:8769/`。服务终端关闭后页面会“拒绝连接”，重新启动即可。也可运行 `python <app>/launch.py --port 8769 --roadshow`，自动尝试后台启动并打开浏览器。Windows后台窗口隐藏；宿主可能回收后台进程，届时使用保留运行的服务终端。不安装开机自启任务。换端口后，coach.py也使用同一端口。

bootstrap拒绝覆盖任何现有目录。每个项目用独立工作目录。当前应用状态写在 `<app>/data/`，不能复制进公开仓库。

## 按需安装

```text
python <skill>/scripts/setup_optional.py --app <app> --check
python <skill>/scripts/setup_optional.py --app <app> --vision
python <skill>/scripts/setup_optional.py --app <app> --asr tiny
```

视觉文件下载到 `<app>/public/vendor`、`public/models`。语音依赖安装到独立 `.venv`，Whisper模型下载到 `<app>/models`，不会升级系统Python。tiny较快，small通常更准但CPU转写更慢、占用更多空间；口音和术语仍需校对。首次安装需要联网；仅下载工具模型，不上传项目材料。使用small可把最后一行的tiny改为small。

安装语音后用 `.venv/Scripts/python.exe server.py`（Windows）或 `.venv/bin/python server.py`（macOS/Linux）启动；launch.py自动优先用此虚拟环境。初始化返回下载成功不等于可识别人脸/语音，启动后仍需用户实际测试。

## 导入PPT

先导出完整逐页图片，按 `01.png、02.png……` 命名。运行：

```text
python <skill>/scripts/import_slides.py --app <app> --images <图片文件夹> --source <源PPT路径>
```

如果文件名不能明确表示顺序，提供 `--order <顺序.json>`，JSON内容为按顺序排列的文件名字符串数组。脚本接受PNG/JPG/JPEG/WEBP；保留源图、不拉伸裁切，生成页序与SHA256清单。更新已有deck需要明确加 `--replace`；旧文件与清单保留。导入时先停止服务，导入后重启，避免旧状态与新PPT混用。

素材准备好后按materials.md填入knowledge.json和glossary.json，重启加载。不要把占位图或示例问题当成真实项目内容。

## 摄像头

用户点击开启，确认画面有本人，而非灰色锁图；灰锁通常应检查物理滑盖/厂商隐私开关。站姿需双肩和胯部入镜，6–12秒稳定校准。允许仅身体校准；无脸部通道不能分析脸部事件。光照/站距变化后重新校准。模型不可用时保持摄像头预览，支持继续文字训练。

## 最小验证

访问 `/api/state`、`/api/roadshow` 和两种网页；核对幻灯片数量和首尾页。没有模型时能键入回答。用独立测试目录检查一次出题、答题、反馈、导出，不重置真实练习记录。
