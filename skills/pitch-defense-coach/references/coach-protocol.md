# 当前聊天与本机网页的协作

不需要另一AI账号或API密钥。Agent读本机记录、思考并通过CLI发下一题；网页负责录音、摄像头、翻页、计时和记录。网页自己不会调用AI。

命令在项目工具目录运行，所有JSON使用UTF-8。先 `python coach.py poll --wait 0 --port 8769`，记录session.id和revision。用户在页面点击开始后，进入waiting_coach才出题。不要重置未完成的会话。

```text
python coach.py question --file question.json --port 8769
python coach.py poll --after <revision> --wait 25 --port 8769
python coach.py feedback --file feedback.json --port 8769
python coach.py report --file report.json --port 8769
```

question.json：
```json
{"sessionId":"实际轮次ID","text":"一个明确问题？","dimension":"项目创新","chainId":"chain-1","source":"题库B01 / PPT P7","candidateChains":[{"id":"chain-1","gap":"缺少对照条件"},{"id":"chain-2","gap":"缺少付费证据"}]}
```

候选链必须来自用户材料，上例仅说明字段。等待用户提交后，以最新answer.text为准，原始ASR供校对。不要把前一轮或尚未提交的文本当成回答。

feedback.json：
```json
{"sessionId":"实际ID","questionId":"Q01","feedback":{"content":"是否直接回答问题","logic":"缺哪一环及影响","evidence":"使用了什么证据/缺什么条件","rewrite":"在现有证据范围内的精简口述示范","nonverbal":["Q01回答第12.0—14.2秒：实际记录的动作、待复核；对应可替换动作"]}}
```

没有有效事件写“未采集到可用非言语证据”，不能编秒数。逐题包含内容、逻辑、证据；改写不引入新的数据。用户校对中不要催促或自动视为答不出。模糊回答必须至少一次证据追问，然后根据回答继续或切换维度。

report.json：
```json
{"sessionId":"实际ID","report":{"summary":"本轮优势与最重要缺口","dimensions":[{"name":"个人成长","level":"中","basis":"关联具体回答与证据"},{"name":"项目创新","level":"弱","basis":"同上"},{"name":"产业价值","level":"缺失","basis":"本轮未覆盖，不能推断没有价值"},{"name":"团队协作","level":"缺失","basis":"本轮未覆盖"}],"priorities":[{"action":"先说对照条件再报结论","practice":"用现有数据卡重答2遍，每遍45秒","check":"两遍均包含同一对照对象、单位和条件","questionIds":["Q01"]},{"action":"补一句本人具体贡献","practice":"以已有记录练30秒版本","check":"有本人动作和产出，非仅团队头衔","questionIds":["Q02"]},{"action":"缩短准备性开头","practice":"回听并删除重复引入，录制两遍","check":"首句10秒内给出核心回答","questionIds":["Q01"]}]}}
```

维度名称与数量使用本轮 `session.ruleWeights`，旧轮次才回退到 `knowledge.ruleWeights`。三创赛常规赛5项、实战赛7项；上例仅为国创赛示范。恰好三个实际适用的优先动作。不得照搬示例诊断。等级是训练证据充分度，不是官方分数；未问到的维度明确“本轮未覆盖”。

## 路演

GET `/api/roadshow` 读取当前session、deck、visits、转写和事件。完整路演按本轮 `limitSeconds` 连续计时，`limitSeconds=null`则不计时专项；期间不提问。结束后转写，本机处理耗时不算路演时间。逐页分析要依据实际页访问和时间戳，跨页句子允许人工核对。串联答辩读取`sourceRoadshow`的已确认副本，不能以后来路演替换来源。模式与API见[训练模式](training-modes.md)。

收到`practiceGoal`后围绕目标提问；不计时专项可在聊天逐题反馈，再用同题或换问法复练。计时模式一般结束后集中反馈。所有模式仍填写逐题反馈与最终报告；未覆盖维度注明本轮未覆盖，不能推断项目没有该优势。

POST `/api/roadshow/report`：`{"sessionId":"实际ID","report":{"summary":"...","pages":[{"page":1,"feedback":"具体内容与时间依据"}],"priorities":[{"action":"...","practice":"...","check":"..."}, {"action":"...","practice":"...","check":"..."}, {"action":"...","practice":"...","check":"..."}]}}`。

## 非言语判定界限

现有实现是启发式事件检测，尚未做群体精度验证。身体侧倾/摇晃、双臂交叉、面部方向偏移、皱眉/抿唇代理、触摸面颈等只作可复核动作观察；正面2D画面不能可靠测量驼背或后仰深度，抿唇不等于咬唇。

动作需持续超过约1.5秒、相关通道有效；相对基线不等于标准体态。缺少有效脸部时只报告身体。音频停顿超过3秒和语速突变来自转写时间戳，必须回听排除识别漏字。不得把任意动作关联为“紧张原因”，只能说它发生于某题的某时段。
