#!/usr/bin/env python3
"""
MedKeep - 极简家庭病历与健康档案后端
(纯原生 Python 3 标准库，0 外部依赖，内存开销 < 20MB)

功能：
1. /api/members                          : 获取配置的家庭成员列表
2. /api/conditions?person={id}           : 专科病情全景纵向聚类 (基于 V2.0 命名与单据字段纯动态汇聚)
3. /api/episodes?person={id}             : 门诊病历为主线精准关联检查检验的临床事件流 (纯动态编排)
4. /api/records?person={id}              : 原始单据全量列表
5. /api/summary                          : 统计概览
6. /records/* & /medicalRecords/*        : 本地高清单据原件静态路由 (0延迟极速加载)
7. / & /index.html                       : 现代化单页看板
"""

import os
import sys
import json
import re
import argparse
import urllib.parse
from collections import defaultdict
from http.server import HTTPServer, SimpleHTTPRequestHandler

ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(ROOT_DIR, "data")
RECORDS_DIR = os.path.join(ROOT_DIR, "records")
VIEWER_DIR = os.path.join(ROOT_DIR, "viewer")
CONFIG_DIR = os.path.join(ROOT_DIR, "config")

# V2.0 命名法标准专科大类元数据映射
CATEGORY_MAPPING = {
    "resp": {"code": "resp", "name": "呼吸专科", "title": "呼吸系统专科诊疗", "icon": "🫁", "theme": "blue"},
    "gi": {"code": "gi", "name": "消化系统", "title": "消化系统专科诊疗", "icon": "🥣", "theme": "amber"},
    "ent": {"code": "ent", "name": "耳鼻咽喉", "title": "耳鼻咽喉专科诊疗", "icon": "👂", "theme": "emerald"},
    "derm": {"code": "derm", "name": "皮肤科", "title": "皮肤科专科诊疗", "icon": "🌿", "theme": "purple"},
    "cv": {"code": "cv", "name": "心血管科", "title": "心血管专科诊疗", "icon": "🫀", "theme": "rose"},
    "ortho": {"code": "ortho", "name": "骨科门诊", "title": "骨科与关节肌肉诊疗", "icon": "🦴", "theme": "slate"},
    "tcm": {"code": "tcm", "name": "中医调理", "title": "中医辨证调理", "icon": "🌱", "theme": "amber"},
    "rheum": {"code": "rheum", "name": "风湿免疫", "title": "风湿免疫专科诊疗", "icon": "🩺", "theme": "indigo"},
    "checkup": {"code": "checkup", "name": "健康体检", "title": "健康体检与综合评估", "icon": "🩺", "theme": "indigo"},
    "ped": {"code": "ped", "name": "儿科门诊", "title": "儿童保健与儿科诊疗", "icon": "👶", "theme": "pink"},
    "eye": {"code": "eye", "name": "眼科门诊", "title": "眼科专科诊疗", "icon": "👁️", "theme": "teal"},
    "general": {"code": "general", "name": "全科综合", "title": "全科综合诊疗", "icon": "📋", "theme": "slate"},
}

THEME_TAG_MAP = {
    "blue": "bg-blue-100 text-blue-800 border-blue-200",
    "amber": "bg-amber-100 text-amber-800 border-amber-200",
    "emerald": "bg-emerald-100 text-emerald-800 border-emerald-200",
    "purple": "bg-purple-100 text-purple-800 border-purple-200",
    "rose": "bg-rose-100 text-rose-800 border-rose-200",
    "slate": "bg-slate-100 text-slate-800 border-slate-200",
    "indigo": "bg-indigo-100 text-indigo-800 border-indigo-200",
    "pink": "bg-pink-100 text-pink-800 border-pink-200",
    "teal": "bg-teal-100 text-teal-800 border-teal-200",
}

def normalize_topic(raw_topic, raw_category=""):
    t = (raw_topic or "").lower().strip()
    c = (raw_category or "").lower().strip()
    aliases = get_config().get("topic_aliases", {})
    if t in aliases and aliases[t] in CATEGORY_MAPPING:
        return CATEGORY_MAPPING[aliases[t]]
    if c in aliases and aliases[c] in CATEGORY_MAPPING:
        return CATEGORY_MAPPING[aliases[c]]
    if t in CATEGORY_MAPPING:
        return CATEGORY_MAPPING[t]
    if c in CATEGORY_MAPPING:
        return CATEGORY_MAPPING[c]
    for k, target in aliases.items():
        if (k in t or k in c) and target in CATEGORY_MAPPING:
            return CATEGORY_MAPPING[target]
    for k, v in CATEGORY_MAPPING.items():
        if k in t or k in c:
            return v
    return {"code": "general", "name": "综合门诊", "title": "综合门诊与辅助检查", "icon": "📋", "theme": "slate"}

def parse_hosp_dept_doctor(h_str):
    parts = [p.strip() for p in (h_str or "").split('·')]
    hosp = parts[0] if len(parts) > 0 and parts[0] else "医疗机构"
    dept = parts[1] if len(parts) > 1 and parts[1] else "门诊"
    doctor = parts[2] if len(parts) > 2 and parts[2] else "门诊医师"
    doctor = re.sub(r'^(问诊医生：|就诊医生：|报告医师：|医师：|送检医师：)', '', doctor).strip()
    return hosp, dept, doctor

def get_config():
    cfg_path = os.path.join(CONFIG_DIR, "medkeep.json")
    if not os.path.exists(cfg_path):
        cfg_path = os.path.join(CONFIG_DIR, "medkeep.template.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "storage": {"mode": "local", "local_records_dir": "./records"},
        "members": [{"id": "demo", "name": "示例成员"}]
    }

def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    cfg_path = os.path.join(CONFIG_DIR, "medkeep.json")
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def get_person_records(person):
    records = []
    cfg = get_config()
    member_ids = [m["id"] for m in cfg.get("members", [])]
    if person == "all":
        targets = member_ids
    else:
        targets = [person]

    for p in targets:
        jsonl_file = os.path.join(DATA_DIR, f"{p}-medical-records.jsonl")
        if not os.path.exists(jsonl_file) and p == "demo":
            jsonl_file = os.path.join(DATA_DIR, "records.sample.jsonl")
            
        if os.path.exists(jsonl_file):
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except Exception:
                            pass
    return records

def get_person_observations(person):
    obs = []
    cfg = get_config()
    member_ids = [m["id"] for m in cfg.get("members", [])]
    if person == "all":
        targets = member_ids
    else:
        targets = [person]

    for p in targets:
        jsonl_file = os.path.join(DATA_DIR, f"{p}-observations.jsonl")
        if not os.path.exists(jsonl_file) and p == "demo":
            jsonl_file = os.path.join(DATA_DIR, "observations.sample.jsonl")

        if os.path.exists(jsonl_file):
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            obs.append(json.loads(line))
                        except Exception:
                            pass
    obs.sort(key=lambda x: x.get("date", ""), reverse=True)
    return obs

def build_episodes(person, records, observations=None):
    """
    根据数据源记录，基于日期和临床主题纯动态编排就诊事件流 (Episodes)。
    - 若当天存在门诊/住院/出院记录 (category in ['visit', 'discharge'])，以此为主线挂载关联报告；
    - 若当天仅有化验或检查，自动聚类为辅助检查事件，并智能标注缺失门诊病历底纸；
    - 若同日有不同科室就诊，按临床主题分别归类挂载。
    """
    obs_list = observations if observations is not None else get_person_observations(person)
    by_date = defaultdict(list)
    for r in records:
        by_date[r.get('date', '')].append(r)

    episodes = []
    seq = 1

    for date in sorted(by_date.keys(), reverse=True):
        if not date:
            continue
        date_records = by_date[date]
        visits = [r for r in date_records if r.get('category') in ['visit', 'discharge']]
        non_visits = [r for r in date_records if r.get('category') not in ['visit', 'discharge']]

        if len(visits) == 0:
            first = non_visits[0]
            top_meta = normalize_topic(first.get('topic'), first.get('category'))
            hosp, dept, doctor = parse_hosp_dept_doctor(first.get('hospital_dept_doctor', ''))
            diag = first.get('diagnosis', '门诊辅助检查').replace('`', '').strip() or '门诊辅助检查'

            all_nas = []
            rec_ids = set()
            for r in non_visits:
                all_nas.extend(r.get('nas_files', []))
                rec_ids.add(r.get('record_id', ''))

            summary = first.get('findings_and_metrics') or first.get('treatment_and_plan') or first.get('chief_complaint_and_history') or f"完成 {len(non_visits)} 项客观辅助检查。"
            summary = re.sub(r'^[-\s*]*(\*\*.*?\*\*[:：]?|\`.*?\`[:：]?)', '', summary).strip()
            if len(summary) > 160:
                summary = summary[:157] + "..."

            linked_obs = [
                o for o in obs_list
                if o.get("promoted_to_clinical_context") and (
                    o.get("date") == date or any(rid in rec_ids for rid in o.get("linked_record_ids", []))
                )
            ]

            missing_items = [{
                "category": "visit",
                "type_label": "病历缺失",
                "title": f"{top_meta['name']}门诊病历底纸",
                "reason": "未见门诊就诊病历底纸，系统依据辅助单据自动归拢归档。"
            }]
            for r in non_visits:
                for m in (r.get("missing_items") or []):
                    missing_items.append(m)

            inferred_records = [r for r in non_visits if r.get("agent_inference")]
            unconfirmed_count = sum(1 for r in inferred_records if not r.get("manual_confirmed", False))

            title = f"{first.get('document_title', '专科检查检验')}（{diag}）" if diag and diag not in first.get('document_title', '') else first.get('document_title', '门诊化验/检查')

            ep = {
                "episode_id": f"EP-{person.upper()}-{seq:02d}",
                "date_range": date,
                "primary_date": date,
                "department": dept if dept != "门诊" else top_meta['name'],
                "hospital": hosp,
                "doctor": doctor,
                "title": title,
                "diagnosis": diag,
                "has_formal_visit": False,
                "created_by_agent": True,
                "visit_record_ids": [],
                "attached_record_ids": [r.get('record_id') for r in non_visits],
                "summary": summary,
                "primary_visit": None,
                "attached_items": non_visits,
                "all_nas_files": all_nas,
                "promoted_observations": linked_obs,
                "missing_items": missing_items,
                "inferred_records": inferred_records,
                "unconfirmed_count": unconfirmed_count,
                "topic_code": top_meta["code"]
            }
            episodes.append(ep)
            seq += 1

        elif len(visits) == 1:
            v = visits[0]
            top_meta = normalize_topic(v.get('topic'), v.get('category'))
            hosp, dept, doctor = parse_hosp_dept_doctor(v.get('hospital_dept_doctor', ''))
            diag = v.get('diagnosis', '见病历记录').replace('`', '').strip() or '见病历记录'

            all_nas = list(v.get('nas_files', []))
            rec_ids = {v.get('record_id', '')}
            for r in non_visits:
                all_nas.extend(r.get('nas_files', []))
                rec_ids.add(r.get('record_id', ''))

            summary = v.get('chief_complaint_and_history') or v.get('treatment_and_plan') or "门诊就医并完成单据归档。"
            summary = re.sub(r'^[-\s*]*(\*\*.*?\*\*[:：]?|\`.*?\`[:：]?)', '', summary).strip()
            if len(summary) > 160:
                summary = summary[:157] + "..."

            linked_obs = [
                o for o in obs_list
                if o.get("promoted_to_clinical_context") and (
                    o.get("date") == date or any(rid in rec_ids for rid in o.get("linked_record_ids", []))
                )
            ]

            missing_items = list(v.get("missing_items") or [])
            for r in non_visits:
                for m in (r.get("missing_items") or []):
                    missing_items.append(m)

            ep_records = [v] + non_visits
            inferred_records = [r for r in ep_records if r.get("agent_inference")]
            unconfirmed_count = sum(1 for r in inferred_records if not r.get("manual_confirmed", False))

            title = f"{v.get('document_title', '门诊病历')}（{diag}）" if diag and diag not in v.get('document_title', '') else v.get('document_title', '门诊病历')

            ep = {
                "episode_id": f"EP-{person.upper()}-{seq:02d}",
                "date_range": date,
                "primary_date": date,
                "department": dept if dept != "门诊" else top_meta['name'],
                "hospital": hosp,
                "doctor": doctor,
                "title": title,
                "diagnosis": diag,
                "has_formal_visit": True,
                "created_by_agent": False,
                "visit_record_ids": [v.get('record_id')],
                "attached_record_ids": [r.get('record_id') for r in non_visits],
                "summary": summary,
                "primary_visit": v,
                "attached_items": non_visits,
                "all_nas_files": all_nas,
                "promoted_observations": linked_obs,
                "missing_items": missing_items,
                "inferred_records": inferred_records,
                "unconfirmed_count": unconfirmed_count,
                "topic_code": top_meta["code"]
            }
            episodes.append(ep)
            seq += 1

        else:
            # 当日存在多次不同专科就诊，按专科大类分别匹配非病历单据
            for v in visits:
                v_meta = normalize_topic(v.get('topic'), v.get('category'))
                hosp, dept, doctor = parse_hosp_dept_doctor(v.get('hospital_dept_doctor', ''))
                diag = v.get('diagnosis', '见病历记录').replace('`', '').strip() or '见病历记录'

                matched_non_visits = []
                for nv in non_visits:
                    nv_meta = normalize_topic(nv.get('topic'), nv.get('category'))
                    if nv_meta["code"] == v_meta["code"]:
                        matched_non_visits.append(nv)

                all_nas = list(v.get('nas_files', []))
                rec_ids = {v.get('record_id', '')}
                for r in matched_non_visits:
                    all_nas.extend(r.get('nas_files', []))
                    rec_ids.add(r.get('record_id', ''))

                summary = v.get('chief_complaint_and_history') or v.get('treatment_and_plan') or "门诊就医并完成单据归档。"
                summary = re.sub(r'^[-\s*]*(\*\*.*?\*\*[:：]?|\`.*?\`[:：]?)', '', summary).strip()
                if len(summary) > 160:
                    summary = summary[:157] + "..."

                linked_obs = [
                    o for o in obs_list
                    if o.get("promoted_to_clinical_context") and (
                        o.get("date") == date or any(rid in rec_ids for rid in o.get("linked_record_ids", []))
                    )
                ]

                missing_items = list(v.get("missing_items") or [])
                for r in matched_non_visits:
                    for m in (r.get("missing_items") or []):
                        missing_items.append(m)

                ep_records = [v] + matched_non_visits
                inferred_records = [r for r in ep_records if r.get("agent_inference")]
                unconfirmed_count = sum(1 for r in inferred_records if not r.get("manual_confirmed", False))

                title = f"{v.get('document_title', '门诊病历')}（{diag}）" if diag and diag not in v.get('document_title', '') else v.get('document_title', '门诊病历')

                ep = {
                    "episode_id": f"EP-{person.upper()}-{seq:02d}",
                    "date_range": date,
                    "primary_date": date,
                    "department": dept if dept != "门诊" else v_meta['name'],
                    "hospital": hosp,
                    "doctor": doctor,
                    "title": title,
                    "diagnosis": diag,
                    "has_formal_visit": True,
                    "created_by_agent": False,
                    "visit_record_ids": [v.get('record_id')],
                    "attached_record_ids": [r.get('record_id') for r in matched_non_visits],
                    "summary": summary,
                    "primary_visit": v,
                    "attached_items": matched_non_visits,
                    "all_nas_files": all_nas,
                    "promoted_observations": linked_obs,
                    "missing_items": missing_items,
                    "inferred_records": inferred_records,
                    "unconfirmed_count": unconfirmed_count,
                    "topic_code": v_meta["code"]
                }
                episodes.append(ep)
                seq += 1

    return episodes

def build_conditions(person, records, observations=None):
    """
    根据动态生成的就诊事件流，纯动态纵向聚合为专科病情大类 (Conditions)。
    - 计算全周期时间跨度 (date_span) 与最新就诊时间；
    - 统计各专科门诊次数与单据份数；
    - 提取最新诊断作为专科状态摘要。
    """
    episodes = build_episodes(person, records, observations)
    by_code = defaultdict(list)
    for ep in episodes:
        c = ep.get('topic_code', 'general')
        by_code[c].append(ep)

    conds = []
    for code, eps in by_code.items():
        eps.sort(key=lambda x: x.get('primary_date', ''), reverse=True)
        dates = [e['primary_date'] for e in eps if e.get('primary_date')]
        latest = dates[0] if dates else ''
        earliest = dates[-1] if dates else ''

        meta = CATEGORY_MAPPING.get(code, {
            "name": code,
            "title": f"{code}专科诊疗与健康管理",
            "icon": "📋",
            "theme": "blue"
        })

        all_nas = []
        rec_count = 0
        unconfirmed_count = 0
        inferred_count = 0
        missing_count = 0
        for e in eps:
            rec_count += (1 if e.get('primary_visit') else 0) + len(e.get('attached_items', []))
            all_nas.extend(e.get('all_nas_files', []))
            unconfirmed_count += e.get('unconfirmed_count', 0)
            inferred_count += len(e.get('inferred_records', []))
            missing_count += len(e.get('missing_items', []))

        latest_diag = eps[0].get('diagnosis', '日常专科随访')
        theme = meta.get("theme", "blue")
        status_tag = THEME_TAG_MAP.get(theme, "bg-blue-100 text-blue-800 border-blue-200")

        conds.append({
            'condition_id': f'COND-{person.upper()}-{code.upper()}',
            'title': meta["title"],
            'short_name': meta["name"],
            'icon': meta["icon"],
            'theme': theme,
            'status': '规范随访中',
            'status_tag': status_tag,
            'summary': f'累计该专科门诊及辅助检查 {len(eps)} 次，客观单据 {rec_count} 份。最近诊断/结论：{latest_diag}。',
            'latest_date': latest,
            'date_span': f'{earliest} ~ {latest}' if earliest != latest else latest,
            'total_episodes': len(eps),
            'total_records': rec_count,
            'unconfirmed_count': unconfirmed_count,
            'inferred_count': inferred_count,
            'missing_count': missing_count,
            'all_nas_files': all_nas,
            'episodes': eps
        })

    conds.sort(key=lambda x: x.get('latest_date', ''), reverse=True)
    return conds

class MedKeepHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/members/update":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len)
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Invalid JSON: {str(e)}"}).encode("utf-8"))
                return

            cfg = get_config()
            members = cfg.get("members", [])

            action = data.get("action", "update")
            if "members" in data and isinstance(data["members"], list):
                cfg["members"] = data["members"]
            elif action == "add":
                new_id = data.get("id", "").strip().lower()
                new_name = data.get("name", "").strip()
                if not new_id or not new_name:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "成员 ID 和姓名不能为空"}).encode("utf-8"))
                    return
                if any(m.get("id") == new_id for m in members):
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": f"成员 ID '{new_id}' 已存在"}).encode("utf-8"))
                    return
                members.append({
                    "id": new_id,
                    "name": new_name,
                    "gender": data.get("gender", ""),
                    "birth_year": data.get("birth_year", ""),
                    "conditions": []
                })
                cfg["members"] = members
                os.makedirs(os.path.join(RECORDS_DIR, new_id), exist_ok=True)
                rec_file = os.path.join(DATA_DIR, f"{new_id}-medical-records.jsonl")
                if not os.path.exists(rec_file):
                    with open(rec_file, "w", encoding="utf-8") as f:
                        pass
                obs_file = os.path.join(DATA_DIR, f"{new_id}-observations.jsonl")
                if not os.path.exists(obs_file):
                    with open(obs_file, "w", encoding="utf-8") as f:
                        pass
            elif action == "delete":
                del_id = data.get("id")
                cfg["members"] = [m for m in members if m.get("id") != del_id]
            else:
                # 单个成员更新: {"id": "demo", "name": "新名字"}
                target_id = data.get("id")
                new_name = data.get("name", "").strip()
                if not target_id or not new_name:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "成员 ID 和姓名不能为空"}).encode("utf-8"))
                    return
                matched = False
                for m in members:
                    if m.get("id") == target_id:
                        m["name"] = new_name
                        if "gender" in data:
                            m["gender"] = data["gender"]
                        if "birth_year" in data:
                            m["birth_year"] = data["birth_year"]
                        matched = True
                        break
                if not matched:
                    members.append({
                        "id": target_id,
                        "name": new_name,
                        "conditions": []
                    })
                cfg["members"] = members

            save_config(cfg)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "members": cfg["members"]}, ensure_ascii=False).encode("utf-8"))
            return

        if path == "/api/records/confirm":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len)
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Invalid JSON: {str(e)}"}).encode("utf-8"))
                return

            person_id = data.get("person", "").strip()
            record_id = data.get("record_id", "").strip()
            if not person_id or not record_id:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "person 与 record_id 不能为空"}, ensure_ascii=False).encode("utf-8"))
                return

            jsonl_file = os.path.join(DATA_DIR, f"{person_id}-medical-records.jsonl")
            if not os.path.exists(jsonl_file) and person_id == "demo":
                jsonl_file = os.path.join(DATA_DIR, "records.sample.jsonl")

            if not os.path.exists(jsonl_file):
                self.send_response(404)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "未找到成员病历数据文件"}, ensure_ascii=False).encode("utf-8"))
                return

            records = []
            updated_record = None
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    if rec.get("record_id") == record_id:
                        if "manual_confirmed" in data:
                            rec["manual_confirmed"] = bool(data["manual_confirmed"])
                        if "agent_inference" in data and data["agent_inference"] is not None:
                            rec["agent_inference"] = str(data["agent_inference"]).strip()
                        updated_record = rec
                    records.append(rec)

            if updated_record is None:
                self.send_response(404)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"未找到记录 {record_id}"}, ensure_ascii=False).encode("utf-8"))
                return

            with open(jsonl_file, "w", encoding="utf-8") as f:
                for rec in records:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "record": updated_record}, ensure_ascii=False).encode("utf-8"))
            return

        self.send_response(404)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps({"error": "Not Found"}).encode("utf-8"))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        
        cfg = get_config()
        members = cfg.get("members", [])
        default_person = members[0]["id"] if members else "demo"
        person = query.get("person", [default_person])[0]

        # 1. 成员列表 API
        if path == "/api/members":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(members, ensure_ascii=False).encode("utf-8"))
            return

        # 1.5. 患者自查与病情分析 API
        if path == "/api/observations":
            obs = get_person_observations(person)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(obs, ensure_ascii=False).encode("utf-8"))
            return

        # 2. 单据原件本地静态服务 (/records/* 或 /medicalRecords/*)
        if path.startswith("/medicalRecords/") or path.startswith("/records/"):
            rel = path
            if rel.startswith("/medicalRecords/"):
                rel = rel[len("/medicalRecords/"):]
            elif rel.startswith("/records/"):
                rel = rel[len("/records/"):]
            
            rel = urllib.parse.unquote(rel)
            img_path = os.path.join(RECORDS_DIR, rel)
            
            if os.path.exists(img_path) and os.path.isfile(img_path):
                mime = "application/octet-stream"
                lower = img_path.lower()
                if lower.endswith(".jpg") or lower.endswith(".jpeg"):
                    mime = "image/jpeg"
                elif lower.endswith(".png"):
                    mime = "image/png"
                elif lower.endswith(".pdf"):
                    mime = "application/pdf"
                elif lower.endswith(".webp"):
                    mime = "image/webp"
                    
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                with open(img_path, "rb") as f:
                    self.wfile.write(f.read())
                return
            else:
                self.send_response(404)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"Image not found locally")
                return

        # 3. 专科病情全景视图 API
        if path == "/api/conditions":
            records = get_person_records(person)
            conds = build_conditions(person, records)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(conds, ensure_ascii=False).encode("utf-8"))
            return

        # 4. 就诊事件流 API (兼容 /api/timeline)
        if path in ["/api/episodes", "/api/timeline"]:
            records = get_person_records(person)
            episodes = build_episodes(person, records)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(episodes, ensure_ascii=False).encode("utf-8"))
            return

        # 5. 全量原始单据列表 API
        if path == "/api/records":
            records = get_person_records(person)
            records.sort(key=lambda x: x.get("date", ""), reverse=True)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(records, ensure_ascii=False).encode("utf-8"))
            return

        # 6. 统计摘要 API
        if path == "/api/summary":
            summary = {}
            for m in members:
                pid = m["id"]
                recs = get_person_records(pid)
                obs = get_person_observations(pid)
                latest_date = max([r.get("date", "") for r in recs]) if recs else None
                summary[pid] = {
                    "id": pid,
                    "name": m.get("name", pid),
                    "count": len(recs),
                    "latest_date": latest_date,
                    "conditions": m.get("conditions", []),
                    "observations_count": len(obs),
                    "promoted_obs_count": len([o for o in obs if o.get("promoted_to_clinical_context")]),
                    "unconfirmed_count": len([r for r in recs if r.get("agent_inference") and not r.get("manual_confirmed", False)])
                }

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(summary, ensure_ascii=False).encode("utf-8"))
            return

        # 7. 静态前端页面
        if path == "/" or path == "/index.html":
            html_path = os.path.join(VIEWER_DIR, "index.html")
            if os.path.exists(html_path):
                with open(html_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(content)
                return

        super().do_GET()

def run():
    parser = argparse.ArgumentParser(description="MedKeep Local Medical Viewer Server")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on (default: 8765)")
    args = parser.parse_args()

    server = HTTPServer(("0.0.0.0", args.port), MedKeepHandler)
    print("=" * 60)
    print(f"MedKeep 家庭病历与健康档案系统已启动")
    print(f"本地访问地址：http://127.0.0.1:{args.port}")
    print(f"技术架构：Python 3 标准库，无外部依赖，内存占用 < 20MB")
    print(f"单据本地直读：{RECORDS_DIR}")
    print(f"数据存储目录：{DATA_DIR}")
    print("=" * 60)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nMedKeep 服务已平稳关闭。")
        server.server_close()

if __name__ == "__main__":
    run()
