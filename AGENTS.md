# MedKeep - AI Agent 行动准则与操作规约

本文件是任何 AI Agent（Cursor、Claude Code、Codex、Antigravity、Windsurf、Trae 等）在接管 `medkeep` 项目时必须强制遵循的运行规范。

---

## 1. 核心定位与技能路由

MedKeep 采用 **Agent-First 原生极简架构**。当用户提出需求时，Agent 应根据意图自动调用 `.agents/skills/` 目录下的专有技能：

| 用户意图 | 自动激活技能 | 核心动作要求 |
| :--- | :--- | :--- |
| 提供新病历照片、体检PDF、化验单、药单 | **`medkeep-intake`**<br>& **`medkeep-archive`** | 1. 确认归属人（未指定则必须先问询）；<br>2. PDF 强制无损转 2400px JPG 并删原件；<br>3. V2.0 命名保存至 `records/{person}/{year}/`；<br>4. 提取全量指标原子追加至 `data/{person}-medical-records.jsonl`。 |
| 查看病历、启动/重启本地看板、调试接口 | **`medkeep-viewer`** | 1. 执行 `python3 server.py`（纯原生标准库，<20MB）；<br>2. 维护就诊事件流（`episodes`）与专科病情大类（`conditions`）聚类。 |
| 询问既往病史、指标对比、看病前小结、用药核对 | **`medkeep-doctor`** | 1. 基于 `data/*.jsonl` 纯文本单一事实来源进行秒级精确检索；<br>2. 提炼结构化指标对比表与医生问诊小结。 |

---

## 2. 必须死守的铁律 (Hard Rules)

### 🚨 铁律一：隐私防线与 Git 安全
- **绝对严禁** 将任何真实病历扫描件、处方、患者姓名及 `data/*.jsonl` 文件提交到公共 Git 仓库！
- 所有真实数据已被 `.gitignore` 严格拦截。在执行 `git add` 或 `git commit` 时，**必须使用 `git status -u` 仔细复核**，仅允许提交代码、模板（`*.template.json`、`*.sample.jsonl`）及公共文档。

### 🚨 铁律二：成员交互防呆（Multi-user Guard）
- 当用户提交新单据但未指明归属人，且单据内名字不清晰时，**严禁自行猜测**！
- 必须主动暂停并与用户确认：
  > “检测到您提交了新单据，请问该病历属于哪位家庭成员？（请参考 `config/medkeep.json` 中的成员列表；若是新成员，请提供英文 ID 与姓名，例如：`father` / `父亲`）”

### 🚨 铁律三：PDF 格式禁令
- 医疗原件**一律使用高清晰度 JPG**（建议长边 2400px，兼顾清晰度与微小体积，单张约 500KB）。
- 严禁将 PDF 直接归档进 `records/`。所有收到的 PDF 必须转换为 JPG 后，**安全删除原始 PDF**。

### 🚨 铁律四：四段式 V2.0 命名规范
归档文件命名必须且只能遵循：
`YYYYMMDD-{type}-{category}-pN.jpg`
- `type`: `visit`（门诊/急诊）, `discharge`（出院）, `lab`（化验单）, `exam`（功能检查）, `imaging`（超声/CT/MRI/影像）, `rx`（处方）, `checkup`（体检）
- `category`: `resp`（呼吸）, `ent`（耳鼻喉）, `gi`（消化）, `derm`（皮肤）, `cv`（心血管）, `rheum`（风湿免疫）, `tcm`（中医）, `ped`（儿科）, `general`（全科）
- `pN`: `p1`, `p2`, `p3`...

---

## 3. 本地优先与云端同步哲学

1. **单机自持**：所有原件图片存放在 `./records/`，结构化数据存放在 `./data/`，单机 100% 离线自闭环。
2. **云盘原生**：若用户需要多端共享或线上 AI（如 ChatGPT、NotebookLM）问诊，建议直接将项目目录放入 Google Drive 或 OneDrive，利用系统级云盘客户端静默同步，无须在代码中编写复杂的网络上传逻辑。
