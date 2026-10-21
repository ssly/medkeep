---
name: medkeep-archive
description: 负责医疗单据的原件规范化处理：单页/双页报告单转高保真 JPG (p1/p2)、多页集合型体检报告保留 PDF、过滤非病历文档（如保险合同）、V2.0 四段式标准化重命名及本地分发归档。
---

# MedKeep - 单据转换与规范命名 Skill (medkeep-archive)

本 Skill 强制执行 MedKeep 医疗原件物理归档的核心标准。

---

## 核心准则

### 1. 格式分级原则（单双页转 JPG vs 多页集合保留 PDF）
- **单页或双页临床报告单（化验单、检查单、门诊病历等）**：拆分为高保真 `.jpg`（300 DPI / 2400px+），通过 `-p1`、`-p2` 标记页码。
- **多页集合型长文档（如完整的年度体检报告 PDF 等）**：**严禁拆分为 JPG**！原样保留 `.pdf` 格式归档（如 `YYYYMMDD-checkup-general.pdf`）。
- **非病历文件过滤（保险合同/保单等）**：商业保险合同、电子保单、投保核保告知等非医疗诊断单据，**严禁录入病历库**。

### 2. V2.0 标准四段式命名规范
所有单据文件名必须且只能遵循以下规则：
```text
YYYYMMDD-{type}-{category}-pN.jpg  （单/双页报告单）
YYYYMMDD-checkup-general.pdf       （多页集合型体检报告）
```
- **第 1 段（日期）**：`YYYYMMDD`（以单据上打印的真实就诊/检查日期为准）。
- **第 2 段（单据类别 `type`）**：
  - `visit`：门诊病历、急诊病历、病程记录
  - `discharge`：出院记录、出院小结
  - `lab`：化验单、血液检测、尿检、便检、微生物培养
  - `exam`：功能检查（心电图、肺功能、听力测听、脑电图）
  - `imaging`：影像学（超声、CT、核磁 MRI、DR/X光、皮肤镜）
  - `rx`：独立处方笺、中药配药单
  - `checkup`：健康体检报告
- **第 3 段（临床主题 `category`）**：
  - `resp` 呼吸 / `ent` 耳鼻喉 / `gi` 消化肠道 / `derm` 皮肤 / `cv` 心血管 / `rheum` 风湿免疫 / `tcm` 中医 / `ped` 儿科 / `eye` 眼科 / `general` 综合
- **第 4 段（页码）**：`p1`, `p2`, `p3`...

### 3. 本地存储分发
- 目标路径格式：`records/{person_id}/{year}/{filename}`
- 例如：`records/demo/2026/20260315-lab-cbc-p1.jpg`
- 存放后验证文件尺寸与可读性，完成物理归档。
