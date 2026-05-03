# astrbot_plugin_blindbox

这是一个面向南京大学行知×开甲学习小组的 AstrBot「抽奖盲盒」插件，任务列表可以直接在 AstrBot WebUI 里编辑。

## 结构

- `main.py`: 插件入口，包含 `Star` 子类和抽取指令，任务内容从配置读取。
- `metadata.yaml`: 插件元数据，AstrBot 会依据它识别插件信息。
- `_conf_schema.json`: 插件配置 schema，任务列表与活动说明都可以在 WebUI 里直接修改。
- `pages/management/`: BlindBox 小组管理页，可以在 WebUI 里直接创建、添加、移除、解散小组，也可以转让组长。
- `requirements.txt`: 插件依赖占位文件。
- `skills/`: 可选的插件内置 Skills 目录。

## 指令

- `/blindbox`：随机抽取一个盲盒任务。
- `/blindbox 学习`：只抽学习类任务。
- `/blindbox 体育`：只抽体育类任务。
- `/blindbox 交流`：只抽交流类任务。
- `/blindbox 吃喝`：只抽吃喝类任务。
- `/blindbox 全部`：从全部任务中随机抽取。
- `/blindbox group create <序号> <组名> [QQ号...]`：新建小组并可同时加入成员。
- `/blindbox group add <序号> <QQ号...>`：给已有小组继续添加成员。
- `/blindbox group remove <序号> <QQ号...>`：从小组移除成员。
- `/blindbox group transfer <序号> <新组长QQ>`：转让组长身份。
- `/blindbox group request-dissolve <序号>`：组长申请解散小组。
- `/blindbox group request-cancel <序号>`：组长取消解散申请。
- `/blindbox submit <任务说明>`：成员提交任务材料，等待 AI 审核。
- 在群里提交材料：仅通过命令 `/blindbox submit <任务说明>` 提交，命令会自动识别消息中的文字与图片并创建待审核记录。
- 在群里直接 @ 机器人不会触发提交。
- `/blindbox group info <序号>`：查看小组信息和本周抽到的任务。
- `/blindbox group list`：查看所有小组。
- `/blindbox me`：查询当前 QQ 号所属小组。
- `/blindbox redraw [分类]`：对当前成员所属小组重抽本周任务。

## 任务方向

插件内置了四类任务：学习类、体育类、交流类、吃喝类。每个任务都会附带一个建议积分，用于后续兑换奖品或评优。

## 配置方式

在 AstrBot WebUI 的插件配置里，可以直接编辑 `任务列表`，对每条任务修改分类、内容、分值和启用状态，也可以修改活动说明文本。这样后续新增或调整盲盒内容时，不需要再手动上传插件文件。

## 小组规则

- 每个 QQ 号只能属于一个小组。
- 创建时的第一个 QQ 号默认是组长。
- 只有组长和本人才能对某个 QQ 号执行 add/remove。
- 组长可以把组长身份转让给同组成员。
- 组长可以在群内申请或取消解散；WebUI 管理页可以直接解散小组。
- WebUI 管理页支持从成员列表里转让组长。
- 每个小组每周只会保留一个盲盒任务。
- 如果本周已经抽过，再次执行抽取会返回当前任务；需要更换时使用 `/blindbox redraw`。
- 当群消息到来时，插件会根据发送者 QQ 号自动识别所属小组并记录到日志。

## AI 接口

- `GET /astrbot_plugin_blindbox/ai/context?group_no=...`：返回某个小组的成员、累计积分、本周任务和提交状态。
- `GET /astrbot_plugin_blindbox/ai/groups`：返回所有小组的 AI 视图。
- `GET /astrbot_plugin_blindbox/ai/submissions?group_no=...`：读取某个小组的提交记录。
- `POST /astrbot_plugin_blindbox/ai/review`：写入 AI 审核结果，并在通过时自动加分。
- `POST /astrbot_plugin_blindbox/submit`：写入一条待审核提交记录，供 AI 后续处理。
- `POST /astrbot_plugin_blindbox/group/export-submissions`：导出某个小组的提交记录和上下文，方便核实。

提交记录会同时保留文字说明、图片链接、提交人、关联任务快照和审核状态，方便后续由 AI 或人工复核。

## 使用

将整个目录放到 AstrBot 的 `data/plugins/astrbot_plugin_blindbox` 下，然后在 AstrBot WebUI 中重载插件即可。
