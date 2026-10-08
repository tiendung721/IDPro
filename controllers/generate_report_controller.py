from __future__ import annotations

import os
import json
import re
import unicodedata
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from common.auth import Actor, get_actor
from common.session_store import SessionStore
from common.ai_model_config import get_dashboard_model
from services.openai_ci import (
    upload_file_for_ci,
    ask_ci_dashboard_spec_tabbed_v3_from_selection,
    ask_ci_dashboard_spec_tabbed_v3_repair,
)

router = APIRouter()
store = SessionStore.get_instance()

_DASHBOARD_VERSION = "dashboard_v4"
_MIN_CHART_WIDGET_TYPES = {"bar", "line", "area", "stacked_bar", "stacked_area", "donut"}
_NON_CHART_WIDGET_TYPES = {
    "summary_card",
    "stat_list",
    "narrative_card",
    "callout",
    "badge_list",
    "table",
    "kpi_row",
    "insight_block",
    "insights",
    "filter_panel",
    "last_updated",
    "last_updated_card",
    "last_updated_widget",
}


# =========================
# Request model
# =========================
class GenerateReportRequest(BaseModel):
    session_id: str = Field(..., min_length=1)

    # UI có thể chọn nhiều report_id; mỗi report_id sẽ sinh ra 1 tab riêng trong spec v3.
    selected_report_ids: List[str] = Field(default_factory=list)

    # params: filters/style/tuỳ chọn UI
    params: Dict[str, Any] = Field(default_factory=dict)

    # Giữ lại để tương thích UI cũ; generate hiện không còn dùng thread continuity
    reset: bool = False


# =========================
# Auth helpers
# =========================
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


# =========================
# JSON parsing + validation
# =========================
def _parse_json_loose(text: str) -> Dict[str, Any]:
    """
    Parse 1 JSON object từ output LLM.
    - Ưu tiên json.loads toàn bộ
    - Fallback: cắt từ '{' đầu tiên đến '}' cuối cùng
    """
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

    decoder = json.JSONDecoder()
    for i, ch in enumerate(s):
        if ch != "{":
            continue
        try:
            obj, _end = decoder.raw_decode(s[i:])
        except Exception:
            continue
        if isinstance(obj, dict):
            return obj

    raise ValueError("Không tìm thấy JSON object trong output")


def _fold_text(value: Any) -> str:
    s = _clean_text(value).lower()
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip()


def _normalize_layout_rows(layout: Any) -> List[List[Dict[str, Any]]]:
    if not isinstance(layout, list) or not layout:
        return []
    first = layout[0]
    if isinstance(first, list):
        return [
            [item for item in row if isinstance(item, dict)]
            for row in layout
            if isinstance(row, list)
        ]
    if isinstance(first, dict) and "columns" in first:
        rows: List[List[Dict[str, Any]]] = []
        for row in layout:
            if not isinstance(row, dict):
                continue
            columns = row.get("columns")
            if isinstance(columns, list):
                rows.append([item for item in columns if isinstance(item, dict)])
        return rows
    return [[item for item in layout if isinstance(item, dict)]]


def _iter_layout_widget_ids(layout: Any) -> List[str]:
    ids: List[str] = []
    for row in _normalize_layout_rows(layout):
        for item in row:
            widget_id = _clean_text(item.get("id"))
            if widget_id:
                ids.append(widget_id)
    return ids


def _widget_type(widget: Any) -> str:
    return _clean_text((widget or {}).get("type")).lower()


def _widget_has_chart_data(widget: Any) -> bool:
    if not isinstance(widget, dict):
        return False
    data = widget.get("data")
    if not isinstance(data, list) or not data:
        return False
    for row in data:
        if isinstance(row, dict) and row:
            return True
        if row not in (None, "", [], {}):
            return True
    return False


def _count_demo_chart_widgets(widgets: Dict[str, Any]) -> List[str]:
    chart_ids: List[str] = []
    for widget_id, widget in (widgets or {}).items():
        if _widget_type(widget) not in _MIN_CHART_WIDGET_TYPES:
            continue
        if not _widget_has_chart_data(widget):
            continue
        chart_ids.append(str(widget_id))
    return chart_ids


def _has_detail_support_widget(widgets: Dict[str, Any]) -> bool:
    for widget in (widgets or {}).values():
        wtype = _widget_type(widget)
        if wtype == "table":
            return True
        if wtype in {"summary_card", "stat_list", "narrative_card", "callout", "badge_list"}:
            return True
    return False


_DASHBOARD_BANNED_DISPLAY_TERMS = (
    "business",
    "dimension",
    "measure",
    "metric",
    "schema",
    "pipeline",
    "backend",
    "parse",
    "detect",
    "t1",
    "t2",
    "t3",
    "auto-generated",
    "auto generated",
    "logic nghiep vu",
)


def _dashboard_text_has_issue(value: Any) -> bool:
    folded = _fold_text(value)
    if not folded:
        return False
    return any(term in folded for term in _DASHBOARD_BANNED_DISPLAY_TERMS)


def _collect_dashboard_quality_issues(
    *,
    spec: Dict[str, Any],
    catalog_by_report_id: Dict[str, Dict[str, Any]],
) -> List[str]:
    issues: List[str] = []
    tabs = spec.get("tabs") if isinstance(spec.get("tabs"), list) else []

    for tab in tabs:
        if not isinstance(tab, dict):
            continue

        report_id = _clean_text(tab.get("report_id"))
        display = tab.get("display") if isinstance(tab.get("display"), dict) else {}
        widgets = tab.get("widgets") if isinstance(tab.get("widgets"), dict) else {}
        layout_rows = _normalize_layout_rows(tab.get("layout"))
        chart_ids = _count_demo_chart_widgets(widgets)
        layout_widget_ids = _iter_layout_widget_ids(tab.get("layout"))
        chart_ids_in_layout = [widget_id for widget_id in layout_widget_ids if widget_id in chart_ids]
        top_two_ids = {
            _clean_text(item.get("id"))
            for row in layout_rows[:2]
            for item in row
            if isinstance(item, dict)
        }

        if len(chart_ids) < 3:
            issues.append(f"{report_id}: tab must have at least 3 valid chart widgets")
        if len(set(chart_ids_in_layout)) < 3:
            issues.append(f"{report_id}: layout must reference at least 3 chart widgets")
        if not any(widget_id in chart_ids for widget_id in top_two_ids):
            issues.append(f"{report_id}: first two layout rows must include a chart")
        if not any(_widget_type(widget) in {"insight_block", "insights"} for widget in widgets.values()):
            issues.append(f"{report_id}: tab must include an insight block")
        if not _has_detail_support_widget(widgets):
            issues.append(f"{report_id}: tab must include a detail table or support block")

        expected_shell_id = _fallback_shell_id(report_id, _clean_text(display.get("form_type")))
        actual_shell_id = _clean_text(display.get("shell_id"))
        if actual_shell_id != expected_shell_id:
            issues.append(f"{report_id}: shell_id must match {expected_shell_id}")

        expected_form_type = _fallback_form_type(report_id)
        actual_form_type = _clean_text(display.get("form_type"))
        if actual_form_type and actual_form_type != expected_form_type:
            issues.append(f"{report_id}: form_type should be {expected_form_type}")

        title = _clean_text(display.get("title") or tab.get("title"))
        subtitle = _clean_text(display.get("subtitle") or tab.get("summary"))
        framework_title = _clean_text(tab.get("framework_title"))
        if not title or "_" in title or _fold_text(title) in {_fold_text(report_id), _fold_text(framework_title)}:
            issues.append(f"{report_id}: title is not user-friendly")
        if not subtitle:
            issues.append(f"{report_id}: subtitle is empty")

        for field_name, value in (
            ("title", title),
            ("subtitle", subtitle),
            ("hero_statement", display.get("hero_statement")),
            ("footer_note", display.get("footer_note")),
        ):
            if _dashboard_text_has_issue(value):
                issues.append(f"{report_id}: {field_name} contains technical or alias text")

        explanation = display.get("explanation") if isinstance(display.get("explanation"), dict) else {}
        for field_name in ("what_is_happening", "what_to_notice", "what_to_do_next"):
            if not _clean_text(explanation.get(field_name)):
                issues.append(f"{report_id}: explanation.{field_name} is empty")

        chart_count = len(chart_ids)
        non_chart_count = sum(
            1 for widget in widgets.values() if _widget_type(widget) in _NON_CHART_WIDGET_TYPES
        )
        if chart_count and non_chart_count > chart_count + 4:
            issues.append(f"{report_id}: tab is too heavy on non-chart widgets")

    deduped: List[str] = []
    seen = set()
    for issue in issues:
        if issue not in seen:
            seen.add(issue)
            deduped.append(issue)
    return deduped


def _validate_dashboard_spec_tabbed_v3(
    spec: Dict[str, Any],
    selected_report_ids: List[str],
    catalog_obj: Dict[str, Any],
) -> None:
    """
    Validate spec v3:
    - version == 3.0
    - có tabs
    - mỗi selected_report_id phải xuất hiện đúng 1 lần
    - tab_id phải khớp mapping trong catalog
    - mỗi tab có các key tối thiểu để renderer không vỡ
    """
    if not isinstance(spec, dict):
        raise ValueError("Spec is not a JSON object")

    if str(spec.get("version", "3.0")).strip() not in ("3.0", "3", "3.0.0", "3.1", "3.1.0"):
        raise ValueError(f"Invalid spec version: {spec.get('version')} (expected '3.0' or '3.1')")

    meta = spec.get("meta")
    if meta is None or not isinstance(meta, dict):
        raise ValueError("Spec missing 'meta' object")

    tabs = spec.get("tabs")
    if not isinstance(tabs, list):
        raise ValueError("Spec missing 'tabs' list")

    if not tabs:
        raise ValueError("Spec có version 3.x nhưng tabs rỗng")

    reports = catalog_obj.get("reports") or []
    if not isinstance(reports, list):
        raise ValueError("Catalog thiếu 'reports'")

    catalog_by_report_id: Dict[str, Dict[str, Any]] = {}
    for item in reports:
        if isinstance(item, dict):
            report_id = (item.get("report_id") or item.get("id") or "").strip()
            if report_id:
                catalog_by_report_id[report_id] = item

    selected_set = {str(x).strip() for x in selected_report_ids if str(x).strip()}
    if not selected_set:
        raise ValueError("selected_report_ids rỗng sau chuẩn hoá")

    found_report_ids: List[str] = []
    seen_report_ids = set()

    for idx, tab in enumerate(tabs):
        if not isinstance(tab, dict):
            raise ValueError(f"tabs[{idx}] không phải object")

        report_id = (tab.get("report_id") or "").strip()
        tab_id = (tab.get("tab_id") or "").strip()
        title = (tab.get("title") or "").strip()
        framework_title = (tab.get("framework_title") or "").strip()

        if not report_id:
            raise ValueError(f"tabs[{idx}] thiếu report_id")
        if not tab_id:
            raise ValueError(f"tabs[{idx}] thiếu tab_id")
        if not title:
            raise ValueError(f"tabs[{idx}] thiếu title")
        if not framework_title:
            raise ValueError(f"tabs[{idx}] thiếu framework_title")

        if report_id not in selected_set:
            raise ValueError(f"Spec sinh report_id ngoài selection: {report_id}")

        if report_id in seen_report_ids:
            raise ValueError(f"Spec bị trùng report_id trong tabs: {report_id}")
        seen_report_ids.add(report_id)

        catalog_item = catalog_by_report_id.get(report_id)
        if not catalog_item:
            raise ValueError(f"report_id không tồn tại trong catalog: {report_id}")

        expected_tab_id = (
            catalog_item.get("tab_id")
            or catalog_item.get("tabId")
            or ""
        ).strip()

        if not expected_tab_id:
            raise ValueError(f"Catalog thiếu tab_id cho report_id: {report_id}")

        if tab_id != expected_tab_id:
            raise ValueError(
                f"report_id '{report_id}' phải map vào tab_id '{expected_tab_id}', "
                f"nhưng model trả '{tab_id}'"
            )

        catalog_framework_title = (
            catalog_item.get("framework_title")
            or catalog_item.get("title")
            or ""
        ).strip()

        if framework_title != catalog_framework_title:
            raise ValueError(
                f"report_id '{report_id}' phải có framework_title '{catalog_framework_title}', "
                f"nhưng model trả '{framework_title}'"
            )

        if title.strip().lower() == framework_title.strip().lower():
            raise ValueError(
                f"tabs[{idx}] đang dùng title trùng framework_title; cần title động theo dữ liệu"
            )

        for k in ("kpis", "layout", "widgets", "data_notes"):
            if k not in tab:
                raise ValueError(f"tabs[{idx}] thiếu key bắt buộc: {k}")

        if not isinstance(tab["kpis"], list):
            raise ValueError(f"tabs[{idx}].kpis phải là list")
        if not isinstance(tab["layout"], list):
            raise ValueError(f"tabs[{idx}].layout phải là list")
        if not isinstance(tab["widgets"], dict):
            raise ValueError(f"tabs[{idx}].widgets phải là object")
        if not isinstance(tab["data_notes"], dict):
            raise ValueError(f"tabs[{idx}].data_notes phải là object")

        widget_ids = set(tab["widgets"].keys())
        for item_id in _iter_layout_widget_ids(tab["layout"]):
            if item_id not in widget_ids:
                raise ValueError(
                    f"tabs[{idx}] layout tham chiáº¿u widget khÃ´ng tá»“n táº¡i: {item_id}"
                        f"tabs[{idx}] layout tham chiếu widget không tồn tại: {item['id']}"
                    )

        found_report_ids.append(report_id)

    missing = selected_set - set(found_report_ids)
    if missing:
        raise ValueError(f"Thiếu tab cho các report đã chọn: {sorted(missing)}")


def _validate_dashboard_spec_tabbed_v3(
    spec: Dict[str, Any],
    selected_report_ids: List[str],
    catalog_obj: Dict[str, Any],
) -> None:
    if not isinstance(spec, dict):
        raise ValueError("Spec is not a JSON object")

    if str(spec.get("version", "3.0")).strip() not in ("3.0", "3", "3.0.0", "3.1", "3.1.0"):
        raise ValueError(f"Invalid spec version: {spec.get('version')} (expected '3.0' or '3.1')")

    meta = spec.get("meta")
    if meta is None or not isinstance(meta, dict):
        raise ValueError("Spec missing 'meta' object")

    tabs = spec.get("tabs")
    if not isinstance(tabs, list) or not tabs:
        raise ValueError("Spec missing valid 'tabs' list")

    reports = catalog_obj.get("reports") or []
    if not isinstance(reports, list):
        raise ValueError("Catalog missing 'reports'")

    catalog_by_report_id: Dict[str, Dict[str, Any]] = {}
    for item in reports:
        if not isinstance(item, dict):
            continue
        report_id = _clean_text(item.get("report_id") or item.get("id"))
        if report_id:
            catalog_by_report_id[report_id] = item

    selected_set = {str(x).strip() for x in selected_report_ids if str(x).strip()}
    if not selected_set:
        raise ValueError("selected_report_ids is empty after normalization")

    found_report_ids: List[str] = []
    seen_report_ids = set()

    for idx, tab in enumerate(tabs):
        if not isinstance(tab, dict):
            raise ValueError(f"tabs[{idx}] is not an object")

        report_id = _clean_text(tab.get("report_id"))
        tab_id = _clean_text(tab.get("tab_id"))
        title = _clean_text(tab.get("title"))
        framework_title = _clean_text(tab.get("framework_title"))

        if not report_id:
            raise ValueError(f"tabs[{idx}] missing report_id")
        if not tab_id:
            raise ValueError(f"tabs[{idx}] missing tab_id")
        if not title:
            raise ValueError(f"tabs[{idx}] missing title")
        if not framework_title:
            raise ValueError(f"tabs[{idx}] missing framework_title")

        if report_id not in selected_set:
            raise ValueError(f"Spec returned report_id outside selection: {report_id}")
        if report_id in seen_report_ids:
            raise ValueError(f"Spec duplicated report_id in tabs: {report_id}")
        seen_report_ids.add(report_id)

        catalog_item = catalog_by_report_id.get(report_id)
        if not catalog_item:
            raise ValueError(f"Unknown report_id in catalog: {report_id}")

        expected_tab_id = _clean_text(catalog_item.get("tab_id") or catalog_item.get("tabId"))
        expected_framework_title = _clean_text(catalog_item.get("framework_title") or catalog_item.get("title"))
        if not expected_tab_id:
            raise ValueError(f"Catalog missing tab_id for report_id: {report_id}")
        if tab_id != expected_tab_id:
            raise ValueError(f"report_id '{report_id}' must map to tab_id '{expected_tab_id}', got '{tab_id}'")
        if framework_title != expected_framework_title:
            raise ValueError(
                f"report_id '{report_id}' must use framework_title '{expected_framework_title}', got '{framework_title}'"
            )
        if _fold_text(title) == _fold_text(framework_title):
            raise ValueError(f"tabs[{idx}] title must not duplicate framework_title")

        for key in ("kpis", "layout", "widgets", "data_notes"):
            if key not in tab:
                raise ValueError(f"tabs[{idx}] missing required key: {key}")

        if not isinstance(tab["kpis"], list):
            raise ValueError(f"tabs[{idx}].kpis must be a list")
        if not isinstance(tab["layout"], list):
            raise ValueError(f"tabs[{idx}].layout must be a list")
        if not isinstance(tab["widgets"], dict):
            raise ValueError(f"tabs[{idx}].widgets must be an object")
        if not isinstance(tab["data_notes"], dict):
            raise ValueError(f"tabs[{idx}].data_notes must be an object")

        widget_ids = set(tab["widgets"].keys())
        for item_id in _iter_layout_widget_ids(tab["layout"]):
            if item_id not in widget_ids:
                raise ValueError(f"tabs[{idx}] layout references unknown widget id: {item_id}")

        found_report_ids.append(report_id)

    missing = selected_set - set(found_report_ids)
    if missing:
        raise ValueError(f"Missing tabs for selected reports: {sorted(missing)}")

    quality_issues = _collect_dashboard_quality_issues(
        spec=spec,
        catalog_by_report_id=catalog_by_report_id,
    )
    if quality_issues:
        raise ValueError("; ".join(quality_issues[:12]))


def _normalize_selected_report_ids(values: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in values or []:
        rid = str(raw or "").strip()
        if not rid or rid in seen:
            continue
        seen.add(rid)
        out.append(rid)
    return out


def _get_allowed_report_ids_from_plan(plan: Dict[str, Any]) -> List[str]:
    options = plan.get("report_options") or []
    out: List[str] = []
    seen = set()
    for item in options:
        if not isinstance(item, dict):
            continue
        rid = str(item.get("report_id", "")).strip()
        if rid and rid not in seen:
            seen.add(rid)
            out.append(rid)
    return out


def _validate_selection_against_plan(selected_report_ids: List[str], plan: Dict[str, Any]) -> None:
    allowed = set(_get_allowed_report_ids_from_plan(plan))
    if not allowed:
        raise ValueError("report_plan không có report_options hợp lệ")
    invalid = [rid for rid in selected_report_ids if rid not in allowed]
    if invalid:
        raise ValueError(f"Selection chứa report_id không nằm trong report_plan: {invalid}")


def _build_report_generation_context_key(
    manifest_hash: str,
    plan_cache_key: str,
    selection: Dict[str, Any],
    dashboard_version: str = _DASHBOARD_VERSION,
) -> str:
    payload = {
        "manifest_hash": manifest_hash,
        "plan_cache_key": plan_cache_key,
        "selection": selection,
        "dashboard_version": dashboard_version,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    import hashlib
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _build_dashboard_summary(spec: Dict[str, Any]) -> Dict[str, Any]:
    meta = spec.get("meta") if isinstance(spec.get("meta"), dict) else {}
    tabs = spec.get("tabs") if isinstance(spec.get("tabs"), list) else []
    tables_used_raw = meta.get("tables_used") or []
    tables_used_normalized = []
    for tu in tables_used_raw:
        if isinstance(tu, dict):
            tables_used_normalized.append(str(tu.get("table_id", "")))
        else:
            tables_used_normalized.append(str(tu))

    tab_summaries = []
    for tab in tabs:
        if not isinstance(tab, dict):
            continue
        kpis = tab.get("kpis") if isinstance(tab.get("kpis"), list) else []
        tab_summaries.append(
            {
                "report_id": str(tab.get("report_id", "")).strip(),
                "tab_id": str(tab.get("tab_id", "")).strip(),
                "title": str(((tab.get("display") or {}).get("title") or tab.get("title") or "")).strip(),
                "framework_title": str(tab.get("framework_title", "")).strip(),
                "kpi_labels": [
                    str(k.get("label", "")).strip()
                    for k in kpis
                    if isinstance(k, dict) and str(k.get("label", "")).strip()
                ],
                "tables_used": tables_used_normalized,
            }
        )
    return {
        "title": str(meta.get("title", "")).strip(),
        "subtitle": str(meta.get("subtitle", "")).strip(),
        "time_range": str(meta.get("time_range", "")).strip(),
        "tables_used": tables_used_normalized,
        "tabs": tab_summaries,
    }


def _repair_dashboard_spec_if_needed(
    *,
    spec: Dict[str, Any],
    file_id: str,
    model: str,
    manifest_text: str,
    catalog_text: str,
    selection_text: str,
    plan_compact_text: str,
    dataset_profile_compact_text: str,
    selected_report_ids: List[str],
    catalog_obj: Dict[str, Any],
    dataset_profile_compact: Dict[str, Any],
) -> tuple[Dict[str, Any], Optional[str], List[str]]:
    try:
        _validate_dashboard_spec_tabbed_v3(
            spec=spec,
            selected_report_ids=selected_report_ids,
            catalog_obj=catalog_obj,
        )
        return spec, None, []
    except Exception as exc:
        issues = [part.strip() for part in str(exc).split(";") if part.strip()]

    raw_out, resp_id = ask_ci_dashboard_spec_tabbed_v3_repair(
        file_id=file_id,
        model=model,
        previous_response_id=None,
        manifest_json=manifest_text,
        report_catalog_json=catalog_text,
        selection_json=selection_text,
        plan_compact_json=plan_compact_text,
        dataset_profile_compact_json=dataset_profile_compact_text,
        current_spec_json=json.dumps(spec, ensure_ascii=False),
        quality_issues_json=json.dumps({"issues": issues}, ensure_ascii=False),
    )
    repaired = _parse_json_loose(raw_out)
    repaired = _normalize_dashboard_spec_for_ui(
        repaired,
        selected_report_ids,
        dataset_profile_compact,
    )
    _validate_dashboard_spec_tabbed_v3(
        spec=repaired,
        selected_report_ids=selected_report_ids,
        catalog_obj=catalog_obj,
    )
    return repaired, resp_id, issues


# =========================
# File reading
# =========================
def _read_text_file(path: str, friendly_name: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Không đọc được {friendly_name}: {e}")


def _read_catalog_text() -> str:
    catalog_path = os.path.join(os.getcwd(), "rule_memory", "report_catalog_v1.json")
    return _read_text_file(catalog_path, "report_catalog_v1.json")


def _read_catalog_obj() -> Dict[str, Any]:
    catalog_text = _read_catalog_text()
    try:
        obj = json.loads(catalog_text)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"report_catalog_v1.json không phải JSON hợp lệ: {e}",
        )
    if not isinstance(obj, dict):
        raise HTTPException(status_code=500, detail="report_catalog_v1.json phải có root object")
    return obj


def _ensure_openai_file_id(data: Any, raw_path: str) -> str:
    """
    Upload file gốc lên OpenAI 1 lần cho session (openai_file_id).
    Nếu thiếu openai_file_id -> upload.
    """
    fid = getattr(data, "openai_file_id", None)
    if fid:
        return fid

    try:
        with open(raw_path, "rb") as f:
            content = f.read()
        fid = upload_file_for_ci(os.path.basename(raw_path), content)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upload file gốc lên OpenAI thất bại: {e}")

    data.openai_file_id = fid

    # reset các thread khác để tránh dùng nhầm ngữ cảnh cũ
    data.qa_prev_response_id = None
    data.final_prev_response_id = None
    data.final_spec_prev_response_id = None

    # generate hiện không còn continuity
    data.generate_prev_response_id = None

    store.upsert(data)
    return fid


def _build_selection(req: GenerateReportRequest) -> Dict[str, Any]:
    """
    Selection JSON gửi vào LLM/CI.
    Có thể mở rộng qua params:
    - params.filters
    - params.style
    - params.top_n
    """
    return {
        "selected_report_ids": _normalize_selected_report_ids(req.selected_report_ids),
        "params": req.params or {},
    }


def _pick_model() -> str:
    return get_dashboard_model()


# =========================
# Text normalization + display shaping
# =========================
_JARGON_REPLACEMENTS = {
    "business-facing": "de doc",
    "business view": "goc nhin de hieu",
    "logic nghiep vu": "cach du lieu dang van hanh",
    "ngon ngu nghiep vu": "cach dien dat de hieu",
    "nghiep vu": "cong viec",
    "business": "nguoi xem",
    "kpi": "chỉ số chính",
    "metric": "chỉ số",
    "metrics": "chỉ số",
    "dimension": "nhóm thông tin",
    "measure": "số liệu",
    "schema": "cấu trúc dữ liệu",
    "widget": "khối hiển thị",
    "anomaly": "điểm bất thường",
    "anomalies": "điểm bất thường",
    "variance": "mức chênh lệch",
    "contribution": "mức đóng góp",
    "segmentation": "chia nhóm",
    "hierarchy": "cấp nhóm",
    "waterfall": "mức thay đổi",
    "sunburst": "cơ cấu phân nhóm",
    "gauge": "mức hoàn thành",
    "combo": "so sánh kết hợp",
    "fact table": "bảng dữ liệu chính",
}

_ALLOWED_SHELL_IDS = {
    "overview_premium",
    "comparison_premium",
    "trend_story",
    "quality_review",
    "ranking_board",
    "ops_command",
    "analysis_lab",
    "detail_explorer",
}


def _safe_dict(v: Any) -> dict:
    return v if isinstance(v, dict) else {}


def _clean_text(v: Any) -> str:
    return str(v or "").strip()


def _rewrite_user_text(value: Any, table_name_map: Dict[str, str] | None = None) -> str:
    s = _clean_text(value)
    if not s:
        return ""
    lower = s.lower()
    for src, dst in _JARGON_REPLACEMENTS.items():
        lower = lower.replace(src, dst)
    s = lower

    if table_name_map:
        for tid, dname in table_name_map.items():
            s = re.sub(rf"\b{re.escape(tid)}\b", dname, s, flags=re.IGNORECASE)
    else:
        s = re.sub(r"\bT\d+\b", "", s, flags=re.IGNORECASE)

    s = re.sub(r"\s+", " ", s).strip(" ,;:-")
    if not s:
        return ""
    return s[0].upper() + s[1:]


def _is_number_like(value: Any) -> bool:
    try:
        num = float(value)
    except Exception:
        return False
    return num == num and num not in {float("inf"), float("-inf")}


def _widget_rows(widget: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = widget.get("data")
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def _pick_chart_field(widget: Dict[str, Any], axis: str, fallback_names: List[str]) -> str:
    rows = _widget_rows(widget)
    if not rows:
        return ""
    enc = widget.get("encoding") if isinstance(widget.get("encoding"), dict) else {}
    key = _clean_text(enc.get(axis))
    if not key and axis == "y":
        key = _clean_text(enc.get("value"))
    if key and any(key in row for row in rows):
        return key
    for name in fallback_names:
        if any(name in row for row in rows):
            return name
    return ""


def _extract_chart_axis_points(widget: Dict[str, Any]) -> tuple[List[str], List[float]]:
    rows = _widget_rows(widget)
    if not rows:
        return [], []

    x_key = _pick_chart_field(widget, "x", ["label", "name", "category", "group", "stage", "period"])
    y_key = _pick_chart_field(widget, "y", ["value", "count", "total", "amount", "score"])
    if not x_key or not y_key:
        return [], []

    labels: List[str] = []
    values: List[float] = []
    for row in rows:
        if x_key not in row or y_key not in row:
            continue
        label = _clean_text(row.get(x_key))
        value = row.get(y_key)
        if not label or not _is_number_like(value):
            continue
        labels.append(label)
        values.append(float(value))
    return labels, values


def _looks_time_bucket(labels: List[str]) -> bool:
    if not labels:
        return False
    patterns = (
        r"^\d{4}$",
        r"^\d{4}[-/]\d{1,2}",
        r"^\d{1,2}[-/]\d{1,2}(?:[-/]\d{2,4})?$",
        r"^(q[1-4]|quy\s*[1-4])\b",
        r"^(thang|month)\s*\d{1,2}\b",
        r"^(tuan|week)\s*\d{1,2}\b",
        r"^(ngay|day)\s*\d{1,2}\b",
    )
    sample = labels[:12]
    matches = 0
    for label in sample:
        norm = _clean_text(label).lower()
        if any(re.search(pattern, norm) for pattern in patterns):
            matches += 1
    return matches >= max(2, len(sample) // 2)


def _can_use_donut_variant(labels: List[str], values: List[float]) -> bool:
    if not labels or not values or len(labels) != len(values):
        return False
    if len(labels) < 3 or len(labels) > 6:
        return False
    if len(set(labels)) != len(labels):
        return False
    positive = [value for value in values if value > 0]
    return len(positive) >= 3 and sum(positive) > 0


def _should_prefer_horizontal_bar(widget_id: str, title: str, labels: List[str], report_id: str) -> bool:
    if report_id in {"performance_ranking", "detailed_transactions"}:
        return True
    ranking_terms = ("top", "bottom", "xep hang", "noi bat", "cao nhat", "thap nhat")
    if any(term in title for term in ranking_terms):
        return True
    if widget_id in {"compare_main", "compare_secondary"} and labels:
        return max(len(label) for label in labels) >= 14
    return bool(labels) and (len(labels) >= 7 or max(len(label) for label in labels) >= 16)


def _diversify_widget_variants(tab: Dict[str, Any]) -> Dict[str, Any]:
    widgets = tab.get("widgets") if isinstance(tab.get("widgets"), dict) else {}
    if not widgets:
        return tab

    report_id = _clean_text(tab.get("report_id"))
    donut_used = False
    new_widgets: Dict[str, Any] = {}

    for wid, widget in widgets.items():
        if not isinstance(widget, dict):
            new_widgets[wid] = widget
            continue

        w2 = dict(widget)
        wtype = _clean_text(w2.get("type")).lower()
        labels, values = _extract_chart_axis_points(w2)
        title = _clean_text(w2.get("title")).lower()
        encoding = _safe_dict(w2.get("encoding"))
        has_color_split = bool(_clean_text(encoding.get("color")))

        if wtype in {"bar", "stacked_bar"}:
            if report_id == "trend_growth" and _looks_time_bucket(labels):
                w2["type"] = "stacked_area" if wtype == "stacked_bar" or has_color_split else "line"
            elif (
                report_id == "operational_status"
                and wid in {"hero_main", "compare_main"}
                and _can_use_donut_variant(labels, values)
                and not donut_used
            ):
                w2["type"] = "donut"
                donut_used = True
            elif (
                report_id in {"breakdown_by_category", "data_quality", "exec_overview"}
                and wid not in {"hero_main", "compare_main"}
                and _can_use_donut_variant(labels, values)
                and not donut_used
            ):
                w2["type"] = "donut"
                donut_used = True

            if _clean_text(w2.get("type")).lower() in {"bar", "stacked_bar"} and _should_prefer_horizontal_bar(
                str(wid),
                title,
                labels,
                report_id,
            ):
                w2["orientation"] = "h"

        new_widgets[wid] = w2

    tab2 = dict(tab)
    tab2["widgets"] = new_widgets
    return tab2


def _fallback_form_type(report_id: str) -> str:
    mapping = {
        "exec_overview": "overview_form",
        "breakdown_by_category": "comparison_form",
        "data_quality": "quality_form",
        "trend_growth": "trend_form",
        "performance_ranking": "comparison_form",
        "operational_status": "progress_form",
        "correlation_distribution": "comparison_form",
        "detailed_transactions": "detail_form",
    }
    return mapping.get(report_id, "overview_form")


def _fallback_shell_id(report_id: str, form_type: str = "") -> str:
    report_mapping = {
        "exec_overview": "overview_premium",
        "breakdown_by_category": "comparison_premium",
        "data_quality": "quality_review",
        "trend_growth": "trend_story",
        "performance_ranking": "ranking_board",
        "operational_status": "ops_command",
        "correlation_distribution": "analysis_lab",
        "detailed_transactions": "detail_explorer",
    }
    form_mapping = {
        "overview_form": "overview_premium",
        "comparison_form": "comparison_premium",
        "trend_form": "trend_story",
        "quality_form": "quality_review",
        "progress_form": "ops_command",
        "detail_form": "detail_explorer",
    }
    return report_mapping.get(report_id) or form_mapping.get(form_type) or "overview_premium"


def _normalize_shell_id(value: Any, report_id: str, form_type: str) -> str:
    shell_id = _clean_text(value).lower().replace("-", "_").replace(" ", "_")
    if shell_id not in _ALLOWED_SHELL_IDS:
        return _fallback_shell_id(report_id, form_type)
    return shell_id


def _normalize_density(value: Any) -> str:
    density = _clean_text(value).lower()
    if density not in {"compact", "comfortable", "dense"}:
        return "comfortable"
    return density


def _rewrite_text_list(values: Any, table_name_map: Dict[str, str], limit: int = 4) -> List[str]:
    raw = values if isinstance(values, list) else []
    out: List[str] = []
    for item in raw:
        text = _rewrite_user_text(item, table_name_map)
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _fallback_badge_items(report_id: str, recommendation: str) -> List[str]:
    badges: List[str] = []
    if recommendation == "recommended":
        badges.append("De xuat uu tien")
    mapping = {
        "exec_overview": "Tong quan",
        "breakdown_by_category": "So sanh nhom",
        "data_quality": "Chat luong du lieu",
        "trend_growth": "Theo doi xu huong",
        "performance_ranking": "Xep hang",
        "operational_status": "Van hanh",
        "correlation_distribution": "Phan tich sau",
        "detailed_transactions": "Tra cuu chi tiet",
    }
    label = mapping.get(report_id)
    if label:
        badges.append(label)
    return badges[:3]


def _fallback_display_title(report_id: str, tab: Dict[str, Any], table_name_map: Dict[str, str]) -> str:
    mapping = {
        "exec_overview": "Tổng quan kết quả",
        "breakdown_by_category": "So sánh giữa các nhóm",
        "data_quality": "Kiểm tra dữ liệu",
        "trend_growth": "Theo dõi theo thời gian",
        "performance_ranking": "Nhóm nổi bật",
        "operational_status": "Theo dõi tiến độ",
        "correlation_distribution": "So sánh giữa các nhóm",
        "detailed_transactions": "Chi tiết để tra cứu",
    }
    return _rewrite_user_text(tab.get("title"), table_name_map) or mapping.get(report_id, "Báo cáo tổng quan")


def _fallback_display_subtitle(report_id: str) -> str:
    mapping = {
        "exec_overview": "Giúp bạn xem nhanh bức tranh chung của dữ liệu.",
        "breakdown_by_category": "Giúp bạn nhìn rõ sự khác nhau giữa các nhóm thông tin chính.",
        "data_quality": "Giúp bạn phát hiện các chỗ còn thiếu hoặc chưa đồng nhất.",
        "trend_growth": "Giúp bạn theo dõi dữ liệu thay đổi ra sao theo từng giai đoạn.",
        "performance_ranking": "Giúp bạn nhận ra nhóm nổi bật và nhóm cần chú ý thêm.",
        "operational_status": "Giúp bạn theo dõi tiến độ và các mục đang cần xử lý thêm.",
        "correlation_distribution": "Giúp bạn nhìn rõ cách dữ liệu phân bố giữa các nhóm.",
        "detailed_transactions": "Hiển thị chi tiết từng mục để dễ tra cứu và đối chiếu.",
    }
    return mapping.get(report_id, "Giúp bạn xem dữ liệu theo cách ngắn gọn và dễ hiểu.")


def _fallback_detail_title(report_id: str) -> str:
    if report_id == "data_quality":
        return "Những phần cần kiểm tra"
    if report_id == "detailed_transactions":
        return "Chi tiết dữ liệu"
    return "Danh sách cần xem thêm"


def _build_table_name_map_from_dataset_profile(dataset_profile_compact: Dict[str, Any]) -> Dict[str, str]:
    out = {}
    tables = dataset_profile_compact.get("tables") if isinstance(dataset_profile_compact, dict) else []
    if not isinstance(tables, list):
        return out
    for t in tables:
        if not isinstance(t, dict):
            continue
        tid = _clean_text(t.get("table_id"))
        dname = _clean_text(t.get("display_name"))
        if tid and dname:
            out[tid] = dname
    return out

def _normalize_display(tab: Dict[str, Any], selected_report_ids: List[str], table_name_map: Dict[str, str]) -> Dict[str, Any]:
    report_id = _clean_text(tab.get("report_id"))
    display = tab.get("display") if isinstance(tab.get("display"), dict) else {}
    form_type = _clean_text(display.get("form_type")) or _fallback_form_type(report_id)
    recommended = "recommended" if report_id in selected_report_ids else "optional"

    raw_highlights = display.get("highlights") if isinstance(display.get("highlights"), list) else []
    highlights = []
    for x in raw_highlights:
        sx = _rewrite_user_text(x, table_name_map)
        if sx:
            highlights.append(sx)
    if not highlights:
        summary = _rewrite_user_text(tab.get("summary"), table_name_map)
        if summary:
            parts = [p.strip() for p in re.split(r"[.;]", summary) if p.strip()]
            highlights = parts[:3]
    if not highlights:
        highlights = [
            "Dữ liệu hiện có đủ thông tin để tạo báo cáo này.",
            "Một vài điểm nổi bật đã được gom lại để dễ theo dõi.",
        ]

    raw_metrics = display.get("metrics") if isinstance(display.get("metrics"), list) else []
    metrics = []
    for item in raw_metrics:
        if not isinstance(item, dict):
            continue
        label = _rewrite_user_text(item.get("label"), table_name_map)
        value = _clean_text(item.get("value"))
        note = _rewrite_user_text(item.get("note"), table_name_map)
        if label and value:
            metrics.append({"label": label, "value": value, "note": note})
    if not metrics:
        for k in (tab.get("kpis") or [])[:4]:
            if not isinstance(k, dict):
                continue
            label = _rewrite_user_text(k.get("label"), table_name_map) or "Chỉ số chính"
            value = str(k.get("value", "-"))
            note = _rewrite_user_text(k.get("delta_label") or k.get("note"), table_name_map)
            metrics.append({"label": label, "value": value, "note": note})

    explanation = display.get("explanation") if isinstance(display.get("explanation"), dict) else {}
    what_is_happening = _rewrite_user_text(explanation.get("what_is_happening") or tab.get("summary"), table_name_map)
    what_to_notice = _rewrite_user_text(explanation.get("what_to_notice") or "Có một vài điểm cần chú ý thêm khi đọc dữ liệu này.", table_name_map)
    what_to_do_next = _rewrite_user_text(explanation.get("what_to_do_next") or "Bạn nên xem thêm phần chi tiết để kiểm tra các mục nổi bật.", table_name_map)
    main_section = display.get("main_section") if isinstance(display.get("main_section"), dict) else {}

    recommendation = _clean_text(display.get("recommendation")).lower()
    if recommendation not in {"recommended", "optional"}:
        recommendation = recommended

    shell_id = _normalize_shell_id(display.get("shell_id"), report_id, form_type)
    density = _normalize_density(display.get("density"))
    badge_items = _rewrite_text_list(display.get("badge_items"), table_name_map, limit=4)
    if not badge_items:
        badge_items = _fallback_badge_items(report_id, recommendation)
    side_notes = _rewrite_text_list(display.get("side_notes"), table_name_map, limit=4)
    if not side_notes:
        side_notes = highlights[:2]
    quick_actions = _rewrite_text_list(display.get("quick_actions"), table_name_map, limit=3)
    hero_statement = _rewrite_user_text(
        display.get("hero_statement") or explanation.get("what_is_happening") or tab.get("summary"),
        table_name_map,
    )

    return {
        "form_type": form_type,
        "shell_id": shell_id,
        "density": density,
        "title": _rewrite_user_text(display.get("title"), table_name_map) or _fallback_display_title(report_id, tab, table_name_map),
        "subtitle": _rewrite_user_text(display.get("subtitle"), table_name_map) or _fallback_display_subtitle(report_id),
        "recommendation": recommendation,
        "badge_items": badge_items,
        "hero_statement": hero_statement,
        "side_notes": side_notes[:4],
        "quick_actions": quick_actions[:3],
        "highlights": highlights[:3],
        "metrics": metrics[:5],
        "main_section": {
            "title": _rewrite_user_text(main_section.get("title"), table_name_map) or "Nội dung chính",
            "description": _rewrite_user_text(main_section.get("description"), table_name_map) or "Phần này giúp bạn nhìn rõ nội dung nổi bật nhất trong báo cáo.",
        },
        "explanation": {
            "what_is_happening": what_is_happening or "Báo cáo này tóm tắt những gì đang xuất hiện trong dữ liệu hiện có.",
            "what_to_notice": what_to_notice,
            "what_to_do_next": what_to_do_next,
        },
        "detail_section_title": _rewrite_user_text(display.get("detail_section_title"), table_name_map) or _fallback_detail_title(report_id),
        "footer_note": _rewrite_user_text(display.get("footer_note"), table_name_map) or "Báo cáo được tổng hợp từ dữ liệu bạn đã tải lên.",
    }


def _normalize_debug_meta(tab: Dict[str, Any], root_meta: Dict[str, Any], table_name_map: Dict[str, str]) -> Dict[str, Any]:
    debug_meta = tab.get("debug_meta") if isinstance(tab.get("debug_meta"), dict) else {}
    data_notes = tab.get("data_notes") if isinstance(tab.get("data_notes"), dict) else {}
    
    tables_used = debug_meta.get("tables_used") or root_meta.get("tables_used") or []
    tables_used_display = []
    for tid in tables_used:
        if isinstance(tid, dict):
            tables_used_display.append(tid)
        else:
            tables_used_display.append({"table_id": tid, "display_name": table_name_map.get(str(tid), str(tid))})

    return {
        "report_id": _clean_text(debug_meta.get("report_id") or tab.get("report_id")),
        "tab_id": _clean_text(debug_meta.get("tab_id") or tab.get("tab_id")),
        "framework_title": _clean_text(debug_meta.get("framework_title") or tab.get("framework_title")),
        "shell_id": _clean_text(_safe_dict(tab.get("display")).get("shell_id")),
        "tables_used": tables_used,
        "tables_used_display": tables_used_display,
        "columns_used": debug_meta.get("columns_used") or {},
        "assumptions": debug_meta.get("assumptions") or data_notes.get("assumptions") or [],
        "data_notes": debug_meta.get("data_notes") or data_notes,
        "filters_raw": debug_meta.get("filters_raw") or tab.get("filters") or [],
        "raw_summary": _clean_text(debug_meta.get("raw_summary") or tab.get("summary")),
    }


def _normalize_dashboard_spec_for_ui(spec: Dict[str, Any], selected_report_ids: List[str], dataset_profile_compact: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(spec, dict):
        return spec
    
    table_name_map = _build_table_name_map_from_dataset_profile(dataset_profile_compact)
    root_meta = spec.get("meta") if isinstance(spec.get("meta"), dict) else {}
    tabs = spec.get("tabs") if isinstance(spec.get("tabs"), list) else []
    new_tabs = []
    for tab in tabs:
        if not isinstance(tab, dict):
            continue
        tab2 = dict(tab)
        # Safeguard: ensure required keys exist for the validator and renderer
        for k in ("kpis", "layout", "widgets", "data_notes"):
            if k not in tab2:
                if k in ("layout", "kpis"):
                    tab2[k] = []
                else:
                    tab2[k] = {}

        tab2 = _diversify_widget_variants(tab2)
        tab2["display"] = _normalize_display(tab2, selected_report_ids, table_name_map)
        tab2["debug_meta"] = _normalize_debug_meta(tab2, root_meta, table_name_map)
        tab2["title"] = tab2["display"]["title"]
        tab2["summary"] = tab2["display"]["subtitle"]
        new_tabs.append(tab2)
    spec2 = dict(spec)
    spec2["version"] = "3.1"
    spec2["tabs"] = new_tabs
    return spec2


# =========================
# Endpoint
# =========================
@router.post("/generate_report")
def generate_report(req: GenerateReportRequest, actor: Actor = Depends(get_actor)) -> Dict[str, Any]:
    data = store.get(req.session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session không tồn tại.")

    _assert_owner(data, actor)

    if not getattr(data, "confirmed", False):
        raise HTTPException(
            status_code=400,
            detail="Session chưa confirm sections. Hãy gọi /confirm_sections trước.",
        )

    normalized_selected_report_ids = _normalize_selected_report_ids(req.selected_report_ids)
    if not normalized_selected_report_ids:
        raise HTTPException(
            status_code=400,
            detail="selected_report_ids rỗng. Hãy chọn ít nhất 1 báo cáo.",
        )

    raw_path: Optional[str] = getattr(data, "file_path", None)
    manifest_path: Optional[str] = getattr(data, "sections_manifest_path", None)
    if not raw_path or not manifest_path:
        raise HTTPException(
            status_code=400,
            detail="Thiếu file_path hoặc sections_manifest_path.",
        )

    # reset được giữ lại để tương thích UI cũ, nhưng generate không còn continuity
    if req.reset:
        data.generated_dashboard_spec = None
        data.generated_dashboard_summary = None
        data.report_generation_context_key = None
        data.report_generation_version = None
        store.upsert(data)

    manifest_text = _read_text_file(manifest_path, "sections_manifest.json")
    catalog_text = _read_catalog_text()
    catalog_obj = _read_catalog_obj()

    report_plan = getattr(data, "report_plan", None)
    report_plan_compact = getattr(data, "report_plan_compact", None)
    if not isinstance(report_plan, dict) or not isinstance(report_plan_compact, dict):
        raise HTTPException(
            status_code=400,
            detail="Session chưa có report_plan hợp lệ. Hãy gọi /report_plan trước khi generate_report.",
        )

    try:
        _validate_selection_against_plan(normalized_selected_report_ids, report_plan)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    openai_file_id = _ensure_openai_file_id(data, raw_path)

    selection = _build_selection(req)
    selection_text = json.dumps(selection, ensure_ascii=False)
    plan_compact_text = json.dumps(report_plan_compact, ensure_ascii=False)
    dataset_profile_compact = getattr(data, "dataset_profile_compact", None) or {}
    dataset_profile_compact_text = json.dumps(dataset_profile_compact, ensure_ascii=False)

    manifest_hash = str(getattr(data, "manifest_hash", "") or "").strip()
    plan_cache_key = str(getattr(data, "report_plan_cache_key", "") or "").strip()
    if not manifest_hash:
        import hashlib
        manifest_hash = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()
        data.manifest_hash = manifest_hash
    context_key = _build_report_generation_context_key(manifest_hash, plan_cache_key, selection)

    cached_spec = getattr(data, "generated_dashboard_spec", None)
    if (
        getattr(data, "report_generation_context_key", None) == context_key
        and isinstance(cached_spec, dict)
    ):
        cached_spec = _normalize_dashboard_spec_for_ui(
            cached_spec,
            normalized_selected_report_ids,
            dataset_profile_compact,
        )
        data.generated_dashboard_spec = cached_spec
        data.generated_dashboard_summary = _build_dashboard_summary(cached_spec)
        data.report_generation_version = _DASHBOARD_VERSION
        store.upsert(data)
        return {
            "spec": cached_spec,
            "response_id": None,
            "openai_file_id": openai_file_id,
            "selection": selection,
            "cached": True,
            "cache_scope": "session_generation",
            "dashboard_summary": data.generated_dashboard_summary,
        }

    model = _pick_model()
    repair_resp_id: Optional[str] = None
    repair_issues: List[str] = []

    try:
        raw_out, resp_id = ask_ci_dashboard_spec_tabbed_v3_from_selection(
            file_id=openai_file_id,
            model=model,
            previous_response_id=None,
            manifest_json=manifest_text,
            report_catalog_json=catalog_text,
            selection_json=selection_text,
            plan_compact_json=plan_compact_text,
            dataset_profile_compact_json=dataset_profile_compact_text,
        )

        spec = _parse_json_loose(raw_out)

        spec = _normalize_dashboard_spec_for_ui(spec, normalized_selected_report_ids, dataset_profile_compact)
        spec, repair_resp_id, repair_issues = _repair_dashboard_spec_if_needed(
            spec=spec,
            file_id=openai_file_id,
            model=model,
            manifest_text=manifest_text,
            catalog_text=catalog_text,
            selection_text=selection_text,
            plan_compact_text=plan_compact_text,
            dataset_profile_compact_text=dataset_profile_compact_text,
            selected_report_ids=normalized_selected_report_ids,
            catalog_obj=catalog_obj,
            dataset_profile_compact=dataset_profile_compact,
        )

    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI Code Interpreter lỗi /generate_report: {e}",
        )

    data.selected_reports = selection
    data.generated_dashboard_spec = spec
    data.generated_dashboard_summary = _build_dashboard_summary(spec)
    data.report_generation_context_key = context_key
    data.report_generation_version = _DASHBOARD_VERSION
    store.upsert(data)

    return {
        "spec": spec,
        "response_id": resp_id,
        "repair_applied": bool(repair_resp_id),
        "repair_response_id": repair_resp_id,
        "repair_issues": repair_issues,
        "openai_file_id": openai_file_id,
        "selection": selection,
        "cached": False,
        "cache_scope": "miss",
        "dashboard_summary": data.generated_dashboard_summary,
    }
