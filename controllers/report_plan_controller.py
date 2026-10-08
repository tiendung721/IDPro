from __future__ import annotations

import os
import json
import hashlib
import re
import unicodedata
from typing import Any, Dict, Optional, List

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from common.auth import Actor, get_actor
from common.session_store import SessionStore
from services.openai_ci import upload_file_for_ci, ask_ci_report_plan, ask_ci_report_plan_repair
from common.ai_model_config import get_report_plan_model
from data_processing.rule_memory import get_fingerprint

router = APIRouter()
store = SessionStore.get_instance()

_REPORT_PLAN_VERSION = "planner_v4"
_REPORT_CATALOG_VERSION = "catalog_v1"


class ReportPlanRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    reset: bool = False


def _owner_key_from_actor(actor: Actor) -> str:
    kind = actor.get("kind")
    if kind == "admin" and actor.get("id"):
        return f"admin:{actor['id']}"
    if kind == "user" and actor.get("id"):
        return f"user:{actor['id']}"
    raise HTTPException(status_code=401, detail="Unauthorized")


def _assert_owner(session_data: Any, actor: Actor) -> None:
    expected = _owner_key_from_actor(actor)
    actual = getattr(session_data, "owner_key", None)
    if actual != expected:
        raise HTTPException(status_code=403, detail="Không có quyền truy cập session này.")


def _parse_json_loose(text: str) -> Dict[str, Any]:
    if not isinstance(text, str):
        raise ValueError("output is not a string")

    s = text.strip()
    if not s:
        raise ValueError("output is empty")

    try:
        obj = json.loads(s)
        if not isinstance(obj, dict):
            raise ValueError("JSON root must be object")
        return obj
    except Exception:
        pass

    # 2) Tìm cặp { } rộng nhất trước khi dùng raw_decode
    decoder = json.JSONDecoder()
    start_idx = s.find("{")
    if start_idx == -1:
        raise ValueError(f"Không tìm thấy JSON object trong output. Snippet: {s[:500]}")

    for i in range(start_idx, len(s)):
        if s[i] != "{":
            continue
        try:
            obj, _end = decoder.raw_decode(s[i:])
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue

    raise ValueError(f"Không tìm thấy JSON object trong output. Snippet: {s[:500]}")


def _load_catalog_obj(catalog_text: str) -> Dict[str, Any]:
    try:
        obj = json.loads(catalog_text)
    except Exception as e:
        raise ValueError(f"Catalog không phải JSON hợp lệ: {e}")

    if not isinstance(obj, dict):
        raise ValueError("Catalog root phải là object")

    reports = obj.get("reports")
    if not isinstance(reports, list):
        raise ValueError("Catalog phải có field 'reports' là list")

    return obj


def _catalog_map(catalog_obj: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    reports = catalog_obj.get("reports") or []
    out: Dict[str, Dict[str, Any]] = {}

    for r in reports:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("report_id", "")).strip()
        if not rid:
            continue
        out[rid] = r

    return out


def _safe_list(v: Any) -> list:
    return v if isinstance(v, list) else []


def _safe_dict(v: Any) -> dict:
    return v if isinstance(v, dict) else {}

def _clean_text(v: Any) -> str:
    return str(v or "").strip()

def _build_table_name_map(plan: Dict[str, Any]) -> Dict[str, str]:
    out = {}
    dp = _safe_dict(plan.get("dataset_profile"))
    for t in _safe_list(dp.get("tables")):
        if not isinstance(t, dict):
            continue
        tid = _clean_text(t.get("table_id"))
        dname = _clean_text(t.get("display_name"))
        if tid and dname:
            out[tid] = dname
    return out

def _replace_table_aliases(text: Any, table_name_map: Dict[str, str]) -> str:
    s = _clean_text(text)
    if not s:
        return ""
    for tid, dname in table_name_map.items():
        s = re.sub(rf"\b{re.escape(tid)}\b", dname, s, flags=re.IGNORECASE)
    return s

def _replace_table_aliases_in_list(values: list, table_name_map: Dict[str, str]) -> list:
    out = []
    for x in values or []:
        sx = _replace_table_aliases(x, table_name_map)
        if sx:
            out.append(sx)
    return out


_PLAN_USER_SAFE_REPLACEMENTS = (
    (r"\bgóc nhìn nghiệp vụ\b", "góc nhìn dễ hiểu"),
    (r"\bngôn ngữ nghiệp vụ\b", "cách diễn đạt dễ hiểu"),
    (r"\blogic nghiệp vụ\b", "cách dữ liệu đang vận hành"),
    (r"\bnghiệp vụ\b", "công việc"),
    (r"\bbusiness-facing\b", "dễ đọc"),
    (r"\bbusiness view\b", "góc nhìn dễ hiểu"),
    (r"\bbusiness\b", "người xem"),
)


def _sanitize_plan_user_text(text: Any, table_name_map: Dict[str, str]) -> str:
    s = _replace_table_aliases(text, table_name_map)
    if not s:
        return ""
    for pattern, repl in _PLAN_USER_SAFE_REPLACEMENTS:
        s = re.sub(pattern, repl, s, flags=re.IGNORECASE)
    s = re.sub(r"\bT\d+\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip(" ,;:-")
    if not s:
        return ""
    return s[0].upper() + s[1:]


def _fold_text(value: Any) -> str:
    s = _clean_text(value).lower()
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip()


_PLAN_BANNED_USER_TERMS = (
    "business",
    "dimension",
    "measure",
    "metric",
    "schema",
    "pipeline",
    "backend",
    "parse",
    "detect",
    "auto-generated",
    "auto generated",
    "logic nghiep vu",
)

_PLAN_GENERIC_REASON_PATTERNS = (
    "phu hop de tao bao cao nay",
    "phu hop voi file hien tai",
    "du lieu hien co phu hop",
    "co du thong tin de tao bao cao",
    "tao bao cao nay",
)


def _count_words(value: Any) -> int:
    return len([part for part in re.split(r"\s+", _clean_text(value)) if part])


def _has_plan_banned_term(text: Any) -> bool:
    folded = _fold_text(text)
    if not folded:
        return False
    return any(term in folded for term in _PLAN_BANNED_USER_TERMS)


def _looks_snake_case_title(text: Any) -> bool:
    s = _clean_text(text)
    if "_" in s:
        return True
    folded = _fold_text(s)
    return bool(folded and re.fullmatch(r"[a-z0-9_]+", folded))


def _is_generic_reason(text: Any) -> bool:
    folded = _fold_text(text)
    if not folded:
        return True
    if _count_words(text) < 7:
        return True
    return any(pattern in folded for pattern in _PLAN_GENERIC_REASON_PATTERNS)


def _validate_plan_display_quality(plan: Dict[str, Any], catalog_text: str) -> List[str]:
    issues: List[str] = []
    catalog_by_id = _catalog_map(_load_catalog_obj(catalog_text))
    report_options = _safe_list(plan.get("report_options"))

    for idx, opt in enumerate(report_options):
        if not isinstance(opt, dict):
            issues.append(f"report_options[{idx}] is not an object")
            continue

        report_id = _clean_text(opt.get("report_id"))
        display = _safe_dict(opt.get("display"))
        title = _clean_text(display.get("title"))
        description = _clean_text(display.get("description"))
        reason = _clean_text(display.get("reason"))
        recommendation = _clean_text(display.get("recommendation")).lower()
        framework_title = _clean_text(_safe_dict(catalog_by_id.get(report_id)).get("framework_title"))
        debug_meta = _safe_dict(opt.get("debug_meta"))
        reason_user_safe = _clean_text(debug_meta.get("reason_user_safe"))

        if not title:
            issues.append(f"{report_id}: display.title is empty")
        if not description:
            issues.append(f"{report_id}: display.description is empty")
        if not reason:
            issues.append(f"{report_id}: display.reason is empty")

        if title and (_count_words(title) < 3 or _count_words(title) > 8):
            issues.append(f"{report_id}: title must have 3-8 words")
        if title and _looks_snake_case_title(title):
            issues.append(f"{report_id}: title looks technical or snake_case")
        if title and (_fold_text(title) == _fold_text(report_id) or _fold_text(title) == _fold_text(framework_title)):
            issues.append(f"{report_id}: title duplicates report_id or framework_title")
        if description and _count_words(description) < 5:
            issues.append(f"{report_id}: description is too short")
        if _is_generic_reason(reason):
            issues.append(f"{report_id}: reason is too generic")
        if recommendation not in {"recommended", "optional"}:
            issues.append(f"{report_id}: recommendation must be recommended or optional")

        for field_name, value in (
            ("title", title),
            ("description", description),
            ("reason", reason),
            ("reason_user_safe", reason_user_safe),
        ):
            folded = _fold_text(value)
            if not folded:
                continue
            if re.search(r"\bt\d+\b", folded):
                issues.append(f"{report_id}: {field_name} exposes table alias")
            if _has_plan_banned_term(value):
                issues.append(f"{report_id}: {field_name} contains banned technical wording")
            if "auto-generated" in folded or "auto generated" in folded:
                issues.append(f"{report_id}: {field_name} mentions auto-generated")

        if title and description and _fold_text(title) == _fold_text(description):
            issues.append(f"{report_id}: title duplicates description")
        if description and reason and _fold_text(description) == _fold_text(reason):
            issues.append(f"{report_id}: description duplicates reason")

    deduped: List[str] = []
    seen = set()
    for issue in issues:
        if issue not in seen:
            seen.add(issue)
            deduped.append(issue)
    return deduped


def _fallback_display_title(rid: str, catalog_item: Dict[str, Any]) -> str:
    title = _clean_text(catalog_item.get("title") or catalog_item.get("framework_title"))
    if title:
        return title
    return rid or "Báo cáo"


def _fallback_display_description(rid: str) -> str:
    mapping = {
        "exec_overview": "Giúp bạn xem nhanh bức tranh tổng thể và những điểm chính cần theo dõi.",
        "trend_over_time": "Giúp bạn theo dõi dữ liệu thay đổi như thế nào theo thời gian.",
        "breakdown_by_category": "Giúp bạn so sánh dữ liệu giữa các nhóm thông tin khác nhau.",
        "top_bottom_items": "Giúp bạn nhận ra những mục nổi bật hoặc cần chú ý thêm.",
        "detailed_transactions": "Hiển thị đầy đủ từng dòng dữ liệu để tra cứu và đối chiếu.",
        "data_quality": "Giúp bạn phát hiện chỗ dữ liệu còn thiếu hoặc chưa đồng nhất.",
    }
    return mapping.get(rid, "Giúp bạn xem dữ liệu theo một góc nhìn rõ ràng và dễ theo dõi.")


def _fallback_display_reason(rid: str) -> str:
    mapping = {
        "exec_overview": "Dữ liệu hiện có đủ thông tin để tóm tắt thành một góc nhìn tổng quan, dễ đọc.",
        "trend_over_time": "Dữ liệu có yếu tố thời gian nên phù hợp để theo dõi diễn biến qua từng giai đoạn.",
        "breakdown_by_category": "Dữ liệu có nhiều nhóm thông tin rõ ràng nên phù hợp để chia ra và so sánh.",
        "top_bottom_items": "Dữ liệu có đủ khác biệt giữa các mục để làm nổi bật nhóm đứng đầu hoặc cần chú ý.",
        "detailed_transactions": "Dữ liệu có đủ chi tiết ở từng dòng nên phù hợp để tra cứu đầy đủ.",
        "data_quality": "Dữ liệu có dấu hiệu cần kiểm tra thêm về độ đầy đủ hoặc tính đồng nhất.",
    }
    return mapping.get(rid, "Dữ liệu hiện có phù hợp để trình bày dưới dạng báo cáo dễ hiểu.")


def _normalize_recommendation(value: Any, rid: str, recommended_ids: set[str]) -> str:
    raw = _clean_text(value).lower()
    if raw in {"recommended", "optional"}:
        return raw
    return "recommended" if rid in recommended_ids else "optional"


def _normalize_dataset_profile(plan: Dict[str, Any]) -> Dict[str, Any]:
    dp = _safe_dict(plan.get("dataset_profile"))
    tables = _safe_list(dp.get("tables"))
    qflags = _safe_list(dp.get("quality_flags"))

    norm_tables = []
    for t in tables:
        if not isinstance(t, dict):
            continue

        norm_tables.append(
            {
                "table_id": str(t.get("table_id", "")).strip(),
                "row_count": int(t.get("row_count", 0) or 0),
                "col_count": int(t.get("col_count", 0) or 0),
                "columns": _safe_list(t.get("columns")),
                "time_cols": _safe_list(t.get("time_cols")),
                "numeric_cols": _safe_list(t.get("numeric_cols")),
                "category_cols": _safe_list(t.get("category_cols")),
                "identifier_cols": _safe_list(t.get("identifier_cols")),
                "measure_cols": _safe_list(t.get("measure_cols")),
                "status_cols": _safe_list(t.get("status_cols")),
                "table_role": str(t.get("table_role", "unknown") or "unknown"),
                "display_name": str(t.get("display_name", "")).strip(),
                "display_name_source": str(t.get("display_name_source", "")).strip(),
                "semantic_hints": _safe_list(t.get("semantic_hints")),
            }
        )

    norm_qflags = []
    for q in qflags:
        if not isinstance(q, dict):
            continue

        sev = str(q.get("severity", "info") or "info")
        if sev not in {"info", "warn", "error"}:
            sev = "info"

        norm_qflags.append(
            {
                "severity": sev,
                "message": str(q.get("message", "")).strip(),
            }
        )

    return {
        "tables": norm_tables,
        "quality_flags": norm_qflags,
    }


def _normalize_catalog_evaluation(
    plan: Dict[str, Any], catalog_by_id: Dict[str, Dict[str, Any]], table_name_map: Dict[str, str]
) -> list:
    items = _safe_list(plan.get("catalog_evaluation"))
    out = []

    for it in items:
        if not isinstance(it, dict):
            continue

        rid = str(it.get("report_id", "")).strip()
        if not rid or rid not in catalog_by_id:
            continue

        fit_level = str(it.get("fit_level", "none") or "none").lower()
        if fit_level not in {"high", "medium", "low", "none"}:
            fit_level = "none"

        decision = str(it.get("decision", "rejected") or "rejected").lower()
        if decision not in {"selected", "rejected"}:
            decision = "rejected"

        fit_score_raw = it.get("fit_score", 0)
        try:
            fit_score = float(fit_score_raw)
        except Exception:
            fit_score = 0.0

        fit_score = max(0.0, min(1.0, fit_score))
        candidate_columns = _safe_dict(it.get("candidate_columns"))

        out.append(
            {
                "report_id": rid,
                "fit_level": fit_level,
                "fit_score": fit_score,
                "decision": decision,
                "evidence": [str(x) for x in _safe_list(it.get("evidence")) if str(x).strip()],
                "evidence_user_safe": [
                    safe_text
                    for safe_text in (
                        _sanitize_plan_user_text(x, table_name_map) for x in _safe_list(it.get("evidence"))
                    )
                    if safe_text
                ],
                "candidate_tables": [str(x) for x in _safe_list(it.get("candidate_tables")) if str(x).strip()],
                "candidate_columns": {
                    "time_cols": [str(x) for x in _safe_list(candidate_columns.get("time_cols")) if str(x).strip()],
                    "measure_cols": [str(x) for x in _safe_list(candidate_columns.get("measure_cols")) if str(x).strip()],
                    "category_cols": [str(x) for x in _safe_list(candidate_columns.get("category_cols")) if str(x).strip()],
                    "identifier_cols": [str(x) for x in _safe_list(candidate_columns.get("identifier_cols")) if str(x).strip()],
                },
                "missing_requirements": [
                    str(x) for x in _safe_list(it.get("missing_requirements")) if str(x).strip()
                ],
            }
        )

    return out


def _normalize_report_options(
    plan: Dict[str, Any], catalog_by_id: Dict[str, Dict[str, Any]], table_name_map: Dict[str, str]
) -> list:
    items = _safe_list(plan.get("report_options"))
    recommended_ids = {
        _clean_text(x) for x in _safe_list(plan.get("recommended_default")) if _clean_text(x)
    }
    out = []

    for it in items:
        if not isinstance(it, dict):
            continue

        rid = _clean_text(it.get("report_id"))
        if not rid or rid not in catalog_by_id:
            continue

        catalog_item = catalog_by_id[rid]
        display = _safe_dict(it.get("display"))
        debug_meta = _safe_dict(it.get("debug_meta"))
        tab_id = _clean_text(debug_meta.get("tab_id") or it.get("tab_id") or catalog_item.get("tab_id"))

        raw_inputs = _safe_list(debug_meta.get("inputs") or it.get("inputs"))
        inputs = []
        for inp in raw_inputs:
            if not isinstance(inp, dict):
                continue
            inputs.append(
                {
                    "key": _clean_text(inp.get("key")),
                    "type": _clean_text(inp.get("type")),
                    "default": inp.get("default", ""),
                }
            )

        reason_technical_text = _clean_text(debug_meta.get("reason_technical") or it.get("reason"))

        out.append(
            {
                "report_id": rid,
                "display": {
                    "title": _sanitize_plan_user_text(
                        _clean_text(display.get("title") or it.get("title")) or _fallback_display_title(rid, catalog_item),
                        table_name_map,
                    ),
                    "description": _sanitize_plan_user_text(
                        _clean_text(display.get("description") or it.get("description")) or _fallback_display_description(rid),
                        table_name_map,
                    ),
                    "reason": _sanitize_plan_user_text(
                        _clean_text(display.get("reason") or it.get("reason")) or _fallback_display_reason(rid),
                        table_name_map,
                    ),
                    "recommendation": _normalize_recommendation(display.get("recommendation"), rid, recommended_ids),
                },
                "debug_meta": {
                    "tab_id": tab_id,
                    "reason_technical": reason_technical_text,
                    "reason_user_safe": _sanitize_plan_user_text(reason_technical_text, table_name_map),
                    "inputs": inputs,
                },
            }
        )

    return out


def _normalize_recommended_default(plan: Dict[str, Any], report_options: list) -> list:
    valid_ids = {
        str(x.get("report_id", "")).strip()
        for x in report_options
        if isinstance(x, dict)
    }

    raw = _safe_list(plan.get("recommended_default"))
    out = []

    for rid in raw:
        rid = str(rid).strip()
        if rid and rid in valid_ids and rid not in out:
            out.append(rid)

    return out


def _normalize_report_plan(plan: Dict[str, Any], catalog_text: str) -> Dict[str, Any]:
    if not isinstance(plan, dict):
        raise ValueError("Plan phải là object")

    catalog_obj = _load_catalog_obj(catalog_text)
    catalog_by_id = _catalog_map(catalog_obj)

    version = str(plan.get("version", "1.0") or "1.0").strip()

    dataset_profile = _normalize_dataset_profile(plan)
    
    table_name_map = {}
    for t in _safe_list(dataset_profile.get("tables")):
        tid = _clean_text(t.get("table_id"))
        dname = _clean_text(t.get("display_name"))
        if tid and dname:
            table_name_map[tid] = dname

    catalog_evaluation = _normalize_catalog_evaluation(plan, catalog_by_id, table_name_map)
    report_options = _normalize_report_options(plan, catalog_by_id, table_name_map)
    recommended_default = _normalize_recommended_default(plan, report_options)

    return {
        "version": version,
        "dataset_profile": dataset_profile,
        "catalog_evaluation": catalog_evaluation,
        "report_options": report_options,
        "recommended_default": recommended_default,
    }


def _build_dataset_profile_compact(plan: Dict[str, Any]) -> Dict[str, Any]:
    dataset_profile = _normalize_dataset_profile(plan)
    tables_out = []
    for t in _safe_list(dataset_profile.get("tables")):
        if not isinstance(t, dict):
            continue
        tables_out.append(
            {
                "table_id": str(t.get("table_id", "")).strip(),
                "row_count": int(t.get("row_count", 0) or 0),
                "col_count": int(t.get("col_count", 0) or 0),
                "time_cols": [str(x) for x in _safe_list(t.get("time_cols")) if str(x).strip()],
                "measure_cols": [str(x) for x in _safe_list(t.get("measure_cols")) if str(x).strip()],
                "category_cols": [str(x) for x in _safe_list(t.get("category_cols")) if str(x).strip()],
                "identifier_cols": [str(x) for x in _safe_list(t.get("identifier_cols")) if str(x).strip()],
                "status_cols": [str(x) for x in _safe_list(t.get("status_cols")) if str(x).strip()],
                "table_role": str(t.get("table_role", "unknown") or "unknown"),
                "display_name": str(t.get("display_name", "")).strip(),
                "display_name_source": str(t.get("display_name_source", "")).strip(),
                "semantic_hints": [str(x) for x in _safe_list(t.get("semantic_hints")) if str(x).strip()],
            }
        )

    qflags_out = []
    for q in _safe_list(dataset_profile.get("quality_flags")):
        if not isinstance(q, dict):
            continue
        msg = str(q.get("message", "")).strip()
        sev = str(q.get("severity", "info") or "info")
        if msg:
            qflags_out.append({"severity": sev, "message": msg})

    return {"tables": tables_out, "quality_flags": qflags_out}


def _build_report_plan_compact(plan: Dict[str, Any], catalog_obj: Dict[str, Any]) -> Dict[str, Any]:
    catalog_by_id = _catalog_map(catalog_obj)
    report_options_by_id = {}
    for opt in _safe_list(plan.get("report_options")):
        if isinstance(opt, dict):
            rid = str(opt.get("report_id", "")).strip()
            if rid:
                report_options_by_id[rid] = opt

    evaluation_by_id = {}
    for ev in _safe_list(plan.get("catalog_evaluation")):
        if isinstance(ev, dict):
            rid = str(ev.get("report_id", "")).strip()
            if rid:
                evaluation_by_id[rid] = ev

    selected_candidates = []
    for rid in [str(x).strip() for x in _safe_list(plan.get("recommended_default")) if str(x).strip()]:
        opt = report_options_by_id.get(rid) or {}
        ev = evaluation_by_id.get(rid) or {}
        catalog_item = catalog_by_id.get(rid) or {}
        selected_candidates.append(
            {
                "report_id": rid,
                "title": _clean_text(_safe_dict(opt.get("display")).get("title") or opt.get("title")),
                "description": _clean_text(_safe_dict(opt.get("display")).get("description") or opt.get("description")),
                "tab_id": _clean_text(_safe_dict(opt.get("debug_meta")).get("tab_id") or catalog_item.get("tab_id")),
                "layout_shell": _clean_text(catalog_item.get("layout_shell")),
                "framework_title": str(catalog_item.get("framework_title", catalog_item.get("title", ""))).strip(),
                "reason": _clean_text(_safe_dict(opt.get("display")).get("reason") or opt.get("reason")),
                "fit_level": str(ev.get("fit_level", "none") or "none").strip(),
                "fit_score": float(ev.get("fit_score", 0) or 0),
                "candidate_tables": [str(x) for x in _safe_list(ev.get("candidate_tables")) if str(x).strip()],
                "focus": {
                    "time_cols": [str(x) for x in _safe_list(_safe_dict(ev.get("candidate_columns")).get("time_cols")) if str(x).strip()],
                    "measure_cols": [str(x) for x in _safe_list(_safe_dict(ev.get("candidate_columns")).get("measure_cols")) if str(x).strip()],
                    "category_cols": [str(x) for x in _safe_list(_safe_dict(ev.get("candidate_columns")).get("category_cols")) if str(x).strip()],
                    "identifier_cols": [str(x) for x in _safe_list(_safe_dict(ev.get("candidate_columns")).get("identifier_cols")) if str(x).strip()],
                },
                "inputs": _safe_list(_safe_dict(opt.get("debug_meta")).get("inputs") or opt.get("inputs")),
            }
        )

    return {
        "recommended_default": [str(x).strip() for x in _safe_list(plan.get("recommended_default")) if str(x).strip()],
        "selected_candidates": selected_candidates,
    }


def _repair_report_plan_if_needed(
    *,
    plan: Dict[str, Any],
    file_id: str,
    model: str,
    manifest_text: str,
    catalog_text: str,
) -> tuple[Dict[str, Any], Optional[str], List[str]]:
    issues = _validate_plan_display_quality(plan, catalog_text)
    if not issues:
        return plan, None, []

    raw_out, resp_id = ask_ci_report_plan_repair(
        file_id=file_id,
        model=model,
        previous_response_id=None,
        manifest_json=manifest_text,
        report_catalog_json=catalog_text,
        current_plan_json=json.dumps(plan, ensure_ascii=False),
        quality_issues_json=json.dumps({"issues": issues}, ensure_ascii=False),
    )
    repaired = _normalize_report_plan(_parse_json_loose(raw_out), catalog_text)
    repaired_issues = _validate_plan_display_quality(repaired, catalog_text)
    if repaired_issues:
        joined = "; ".join(repaired_issues[:10])
        raise ValueError(f"Plan repair failed quality gate: {joined}")
    return repaired, resp_id, issues


def _read_df_for_similarity(file_path: str, confirmed_sheet_name: Optional[str]) -> pd.DataFrame:
    lower = (file_path or "").lower()

    if lower.endswith(".csv"):
        return pd.read_csv(file_path, header=None)

    if lower.endswith((".xlsx", ".xls", ".xlsm")):
        return pd.read_excel(
            file_path,
            sheet_name=confirmed_sheet_name if confirmed_sheet_name else 0,
            header=None,
        )

    raise ValueError(f"Unsupported file type for similarity fingerprint: {file_path}")


def _build_similarity_key(raw_path: str, confirmed_sheet_name: Optional[str]) -> str:
    df = _read_df_for_similarity(raw_path, confirmed_sheet_name)
    return get_fingerprint(df, sheet_name=confirmed_sheet_name)


def _get_global_exact_cache(cache_key: str) -> Optional[Dict[str, Any]]:
    fn = getattr(store, "get_report_plan_exact", None)
    if callable(fn):
        try:
            obj = fn(cache_key)
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None


def _put_global_exact_cache(
    cache_key: str, file_hash: str, manifest_hash: str, plan: Dict[str, Any]
) -> None:
    fn = getattr(store, "put_report_plan_exact", None)
    if callable(fn):
        try:
            fn(cache_key, file_hash, manifest_hash, plan)
        except Exception:
            pass


def _get_global_similar_cache(similarity_key: str, manifest_hash: str) -> Optional[Dict[str, Any]]:
    fn = getattr(store, "get_report_plan_similar", None)
    if callable(fn):
        try:
            obj = fn(similarity_key, manifest_hash)
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None


def _put_global_similar_cache(similarity_key: str, manifest_hash: str, plan: Dict[str, Any]) -> None:
    fn = getattr(store, "put_report_plan_similar", None)
    if callable(fn):
        try:
            fn(similarity_key, manifest_hash, plan)
        except Exception:
            pass


@router.post("/report_plan")
def report_plan(req: ReportPlanRequest, actor: Actor = Depends(get_actor)) -> Dict[str, Any]:
    data = store.get(req.session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session không tồn tại.")
    _assert_owner(data, actor)

    if not getattr(data, "confirmed", False):
        raise HTTPException(
            status_code=400,
            detail="Session chưa confirm sections. Hãy gọi /confirm_sections trước.",
        )

    raw_path: Optional[str] = getattr(data, "file_path", None)
    manifest_path: Optional[str] = getattr(data, "sections_manifest_path", None)

    if not raw_path or not manifest_path:
        raise HTTPException(status_code=400, detail="Thiếu file_path hoặc sections_manifest_path.")

    if req.reset:
        data.report_plan = None
        data.report_plan_compact = None
        data.report_plan_cache_key = None
        data.report_plan_similarity_key = None
        data.report_plan_version = None
        data.report_catalog_version = None
        data.generated_dashboard_spec = None
        data.generated_dashboard_summary = None
        data.report_generation_context_key = None
        data.report_generation_version = None
        store.upsert(data)

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_text = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Không đọc được sections_manifest.json: {e}")

    catalog_path = os.path.join(os.getcwd(), "rule_memory", "report_catalog_v1.json")
    try:
        with open(catalog_path, "r", encoding="utf-8") as f:
            catalog_text = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Không đọc được report_catalog_v1.json: {e}")

    file_hash = getattr(data, "file_hash", None) or ""
    manifest_hash = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()
    exact_cache_key = f"{file_hash}:{manifest_hash}:{_REPORT_CATALOG_VERSION}:{_REPORT_PLAN_VERSION}"

    confirmed_sheet_name = getattr(data, "confirmed_sheet_name", None)
    try:
        similarity_key = _build_similarity_key(raw_path, confirmed_sheet_name)
    except Exception:
        similarity_key = ""

    # 1) Session cache
    if (
        getattr(data, "report_plan_cache_key", None) == exact_cache_key
        and isinstance(getattr(data, "report_plan", None), dict)
    ):
        catalog_obj = _load_catalog_obj(catalog_text)
        data.report_plan = _normalize_report_plan(getattr(data, "report_plan", None), catalog_text)
        if not isinstance(getattr(data, "report_plan_compact", None), dict):
            data.report_plan_compact = _build_report_plan_compact(data.report_plan, catalog_obj)
        else:
            data.report_plan_compact = _build_report_plan_compact(data.report_plan, catalog_obj)
        if not isinstance(getattr(data, "dataset_profile_compact", None), dict):
            data.dataset_profile_compact = _build_dataset_profile_compact(data.report_plan)
        else:
            data.dataset_profile_compact = _build_dataset_profile_compact(data.report_plan)
        data.manifest_hash = manifest_hash
        data.report_plan_version = _REPORT_PLAN_VERSION
        data.report_catalog_version = _REPORT_CATALOG_VERSION
        store.upsert(data)
        return {
            "plan": data.report_plan,
            "plan_compact": data.report_plan_compact,
            "dataset_profile_compact": data.dataset_profile_compact,
            "cached": True,
            "cache_scope": "session",
            "cache_key": exact_cache_key,
        }

    # 2) Global exact cache
    cached_exact = _get_global_exact_cache(exact_cache_key)
    if isinstance(cached_exact, dict):
        catalog_obj = _load_catalog_obj(catalog_text)
        cached_exact = _normalize_report_plan(cached_exact, catalog_text)
        data.report_plan = cached_exact
        data.report_plan_compact = _build_report_plan_compact(cached_exact, catalog_obj)
        data.dataset_profile_compact = _build_dataset_profile_compact(cached_exact)
        data.manifest_hash = manifest_hash
        data.report_plan_cache_key = exact_cache_key
        data.report_plan_similarity_key = similarity_key or None
        data.report_plan_version = _REPORT_PLAN_VERSION
        data.report_catalog_version = _REPORT_CATALOG_VERSION
        store.upsert(data)

        return {
            "plan": cached_exact,
            "plan_compact": data.report_plan_compact,
            "dataset_profile_compact": data.dataset_profile_compact,
            "cached": True,
            "cache_scope": "global_exact",
            "cache_key": exact_cache_key,
        }

    # 3) Global similar cache
    if similarity_key:
        cached_similar = _get_global_similar_cache(similarity_key, manifest_hash)
        if isinstance(cached_similar, dict):
            catalog_obj = _load_catalog_obj(catalog_text)
            cached_similar = _normalize_report_plan(cached_similar, catalog_text)
            data.report_plan = cached_similar
            data.report_plan_compact = _build_report_plan_compact(cached_similar, catalog_obj)
            data.dataset_profile_compact = _build_dataset_profile_compact(cached_similar)
            data.manifest_hash = manifest_hash
            data.report_plan_cache_key = exact_cache_key
            data.report_plan_similarity_key = similarity_key
            data.report_plan_version = _REPORT_PLAN_VERSION
            data.report_catalog_version = _REPORT_CATALOG_VERSION
            store.upsert(data)

            return {
                "plan": cached_similar,
                "plan_compact": data.report_plan_compact,
                "dataset_profile_compact": data.dataset_profile_compact,
                "cached": True,
                "cache_scope": "global_similar",
                "cache_key": exact_cache_key,
                "similarity_key": similarity_key,
            }

    # ensure file_id
    if not getattr(data, "openai_file_id", None):
        try:
            with open(raw_path, "rb") as f:
                content = f.read()
            fid = upload_file_for_ci(os.path.basename(raw_path), content)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Upload file gốc lên OpenAI thất bại: {e}")

        data.openai_file_id = fid
        # invalidate other continuities
        data.qa_prev_response_id = None
        data.qa_thread_turn_count = 0
        data.qa_memory_summary = None
        data.qa_recent_turns = []
        data.final_prev_response_id = None
        data.final_spec_prev_response_id = None
        store.upsert(data)

    model = get_report_plan_model()
    repair_resp_id: Optional[str] = None
    repair_issues: List[str] = []

    try:
        raw_out, resp_id = ask_ci_report_plan(
            file_id=data.openai_file_id,
            model=model,
            previous_response_id=None,
            manifest_json=manifest_text,
            report_catalog_json=catalog_text,
        )
        plan_raw = _parse_json_loose(raw_out)
        plan = _normalize_report_plan(plan_raw, catalog_text)
        plan, repair_resp_id, repair_issues = _repair_report_plan_if_needed(
            plan=plan,
            file_id=data.openai_file_id,
            model=model,
            manifest_text=manifest_text,
            catalog_text=catalog_text,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenAI Code Interpreter lỗi /report_plan: {e}")

    catalog_obj = _load_catalog_obj(catalog_text)
    data.report_plan = plan
    data.report_plan_compact = _build_report_plan_compact(plan, catalog_obj)
    data.dataset_profile_compact = _build_dataset_profile_compact(plan)
    data.manifest_hash = manifest_hash
    data.report_plan_cache_key = exact_cache_key
    data.report_plan_similarity_key = similarity_key or None
    data.report_plan_version = _REPORT_PLAN_VERSION
    data.report_catalog_version = _REPORT_CATALOG_VERSION
    store.upsert(data)

    _put_global_exact_cache(
        cache_key=exact_cache_key,
        file_hash=file_hash,
        manifest_hash=manifest_hash,
        plan=plan,
    )

    if similarity_key:
        _put_global_similar_cache(
            similarity_key=similarity_key,
            manifest_hash=manifest_hash,
            plan=plan,
        )

    return {
        "plan": plan,
        "plan_compact": data.report_plan_compact,
        "dataset_profile_compact": data.dataset_profile_compact,
        "cached": False,
        "cache_scope": "miss",
        "cache_key": exact_cache_key,
        "response_id": resp_id,
        "repair_applied": bool(repair_resp_id),
        "repair_response_id": repair_resp_id,
        "repair_issues": repair_issues,
        "openai_file_id": data.openai_file_id,
    }
