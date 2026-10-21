---
name: medkeep-intake
description: 负责家庭病历与病情观察的双轨建档调度、成员识别与单一事实来源 (JSONL) 规范化写入。支持医院正式单据与患者个人自查分析的分流存储与手动打标引用。
---

# MedKeep - 成员调度与双轨数据录入 Skill (medkeep-intake)

本 Skill 是 MedKeep 系统的进门调度中心，死守三大核心机制：**成员交互防呆**、**医院正式单据与患者自查双轨隔离** 以及 **自查分析手动打标确认**。

---

## 核心机制一：双轨数据隔离架构 (Dual-Track Architecture)

为了保证医疗数据的严肃性与客观性，**严禁将患者主观病情分析或日常自测直接写入医院正式病历库**：

| 数据轨道 | 存储文件 | 数据性质 | 典型内容 |
| :--- | :--- | :--- | :--- |
| **轨道 A：医院正式客观单据** | `data/{person}-medical-records.jsonl` | 具备法律与医疗效力的官方单据 | 门诊病历、急诊记录、检验化验报告单、影像诊断单、处方笺、体检报告 |
| **轨道 B：患者病情观察与自查分析** | `data/{person}-observations.jsonl` | 患者自主观察、现象推测与日常自测记录 | 症状起病诱因推测、药物不良反应自查、冷热刺激反应、家庭血压/心率日记 |

---

## 核心机制二：自查分析手动打标确认协议 (Manual Promotion Protocol)

每当用户口述或记录一段病情观察、症状现象或自查推测时，Agent 必须执行以下流程：

1. **结构化提取**至 `data/{person}-observations.jsonl`：
   ```json
   {
     "obs_id": "OBS-DEMO-20260314-01",
     "person": "demo",
     "person_name": "张三（示例）",
     "date": "2026-03-14",
     "datetime": "2026-03-14 21:00",
     "topic": "resp",
     "title": "降温后夜间干咳与冷空气刺激观察",
     "phenomenon": "昨日气温骤降8度，晚间开窗通风后出现持续干咳，无发热无咳痰...",
     "self_analysis": "怀疑冷空气刺激诱发气道高反应性，拟前往三甲医院呼吸内科查血常规与听诊",
     "promoted_to_clinical_context": true,
     "linked_record_ids": ["DEMO-01", "DEMO-02"],
     "created_at": "2026-03-14T21:00:00Z"
   }
   ```

2. **强制主动向用户发起确认（必须征得用户同意方可打标）**：
   > 💡 **已为您保存该条病情自查分析**（编号：`OBS-DEMO-20260314-01`）
   > 
   > **请确认**：是否将该条记录标记为 **【正式临床引用】（Promote to Clinical Context）**？
   > - **若确认打标为【是】**（`promoted_to_clinical_context: true`）：后续生成门诊病史摘要、专科病情看板及医生问诊流会自动将其作为**关键患者自述病史**交叉引用；
   > - **若暂不打标【否】**（`promoted_to_clinical_context: false`）：仅保留在个人观察库中备忘，不干扰后续正式就诊时间线。

---

## 核心机制三：家庭成员识别与防呆

1. **核验既有成员**：
   - 读取 `config/medkeep.json`（若无则读取 `config/medkeep.template.json`）中的 `members` 列表。
   - 若用户输入已明确成员（如配置文件中已存在的成员姓名或拼音/英文 ID），直接提取其英文标识（`id`）。
2. **问询防呆**：
   - 若用户未指明人员且材料中名字模糊，**必须暂停并询问**：
     > “检测到您提交了新内容，请问该记录属于哪位家庭成员？（请参考 `config/medkeep.json` 中的成员列表；若是新成员，请输入英文ID与姓名，例如：`father` / `父亲`）”
3. **新成员自动建档**：
   - 向 `config/medkeep.json` 追加新成员；
   - 自动初始化 `data/{id}-medical-records.jsonl` 与 `data/{id}-observations.jsonl`。
