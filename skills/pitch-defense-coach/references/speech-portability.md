# 语音环境发现、复用与平台边界

## 首次启动，不等于首次下载

读取用户已有实例优先。`server.py`启动时先离线发现并真实加载验证：当前实例配置及models/runtime/.venv、同一父目录下已有训练实例、用户共享登记表、Hugging Face标准缓存中的Systran faster-whisper small/tiny。不会递归搜索整台电脑，也不会读取其他项目题库、录音或训练记录。最多检查80个同级目录、每型号8个缓存版本，探测预算约40秒；未发现不等于电脑其他目录绝对没有。

模型必须是支持的faster-whisper/CTranslate2格式，且对应Python环境可以导入依赖并实际加载模型。只有一个model.bin、OpenAI Whisper的.pt文件、whisper.cpp的GGML/GGUF文件不能直接宣称可复用。Python环境可能因操作系统、架构或解释器版本不兼容而失败；此时可保留兼容模型文件，只补装依赖。

检测成功写入实例根目录`speech-resources.json`，引用已有模型和Python路径，不复制大文件，不重新下载。直接运行`server.py`也会检测；如需换到已验证的本机Python，会在启动服务前切换。模型加载验证不等于口音识别效果已验证，仍需录一段真实发言校对。

由Agent部署时可先运行：

```text
python <skill>/scripts/setup_optional.py --app <app> --discover
```

旧模型在其他位置时，明确指定其训练实例根目录：

```text
python <skill>/scripts/setup_optional.py --app <app> --discover --reuse-from <旧实例目录> --register
```

`--register`将通过验证的模型、解释器和依赖路径记在`~/.cache/pitch-defense-coach/speech-resources.json`；不同Agent只要使用同一系统用户、可访问同一文件系统，就可发现它。可用`PDC_SPEECH_REGISTRY`指定登记表位置。登记不包含项目材料，绝不提交到GitHub；宿主限制读取/写入这些位置时按其权限流程处理。共享登记不是跨电脑同步，容器/另一系统用户不会自动拥有宿主路径。

## 没找到时的选择

网页发现`needsSetup`后显示“启用本机语音转写？”对话框：准确优先版、轻量快速版、暂不安装。用户选择保存到`data/speech-setup-choice.json`并进入`/api/state`的`speechSetup`。关闭或跳过不视为授权，不阻止文字答辩和计时；页面可以重新打开安装选项。

页面只记录选择，不在HTTP接口里执行下载或任意系统命令。当前Agent读取`requested`后说明安装将联网下载依赖及缺失模型、占用本机磁盘；用户已明确选择的版本无需重复询问，但仍须满足宿主权限。执行：

```text
python <skill>/scripts/setup_optional.py --app <app> --asr small --yes --register
```

快速版将small换为tiny。脚本仍先查找可用环境，能复用则不安装；有完整模型但缺依赖时只安装独立`.venv`依赖，不重复下载模型。非交互运行没有`--yes`会返回`confirmation_required`，不安装；终端交互默认为不安装。`--yes`仅能用于已有用户同意的情况，不能因没有TTY或网页关闭而补写。

安装成功后通过真实加载验证才报告成功。等待用户当前录音/训练结束后，用launch.py重启同一实例并刷新页面确认“已就绪”；不强制终止用户训练。不额外复制原项目词表到别人的项目。仍提示失败时保留材料并说明具体缺项，不反复下载。

没有持续运行的Agent时，点击选择不会自动完成安装。提示用户回聊天发送“完成语音安装”；没有命令执行能力的平台，需要用户在本机终端执行已确认的安装步骤。

## 其他Agent平台

Skill采用[Agent Skills目录规范](https://agentskills.io/specification)，语音使用开源[faster-whisper](https://github.com/SYSTRAN/faster-whisper)，不要求某家AI API密钥。兼容性分两层：

| 宿主能力 | 可用范围 |
| --- | --- |
| 能读取Skill并执行本机Python、管理本机文件、打开本地浏览器 | 可部署完整工具；摄像头/麦克风由浏览器请求授权。Agent能调用本机API或coach.py时可实时接入出题和反馈 |
| 能执行命令，但只在远程容器/云端环境中 | 可做材料分析或在远端转写，但不能自动访问用户电脑模型/摄像头；如要求音视频不离开本机，必须把服务部署在用户电脑，并建立经授权的交接方式，不默认上传录音 |
| 仅聊天、无法执行程序或启动本地服务 | 可做文字模拟与复盘；不能仅靠安装Skill承诺自动语音、摄像头或后台计时 |

Windows本机已验证加载与服务流程；macOS/Linux路径处理已实现，但未做这两类设备实测。不要宣称所有Agent、系统或手机平台均即装即用。`agents/openai.yaml`只是可选界面元数据，核心程序不依赖它；其他宿主的安装入口及权限以自身文档为准。
