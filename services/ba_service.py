import json
import math
from typing import Any, Dict, List, Optional

from common.ba_models import BADetectionResult, BAAnalysisResult, QuotationRenderResult
from services.openai_ci import ask_ci_ba_detection, ask_ci_ba_analysis


_DRIVER_LABELS = {
    "users": "Số người dùng",
    "branches": "Số chi nhánh",
    "sites": "Số địa điểm",
    "warehouses": "Số kho",
    "stores": "Số cửa hàng",
    "integrations": "Kết nối tích hợp",
    "environments": "Môi trường vận hành",
}

_LEVEL_LABELS = {
    "low": "Thấp",
    "medium": "Trung bình",
    "high": "Cao",
    "unknown": "Chưa rõ",
}

_REVIEW_DETAIL_KEYS = {
    "reason",
    "ambiguity_reason",
    "note",
    "notes",
    "remarks",
    "issue",
    "message",
    "status",
}

_REVIEW_TEXT_KEYS = [
    "requirement_name",
    "feature_name",
    "module_name",
    "item_name",
    "title",
    "text",
    "description",
    "raw_text",
    "name",
]

_SOURCE_KEYS = {
    "source_table_id",
    "source_row_numbers",
    "row_numbers",
    "rows",
    "source_rows",
}


def parse_json_object(text: str) -> Dict[str, Any]:
    if not isinstance(text, str):
        raise ValueError("output is not a string")
    s = text.strip()
    if not s:
        raise ValueError("AI trả về phản hồi rỗng (Empty Response)")

    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

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


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == "" or value.strip().lower() in {"unknown", "none", "null", "n/a"}
    if isinstance(value, float):
        return math.isnan(value)
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def _humanize_key(key: str) -> str:
    if key in _DRIVER_LABELS:
        return _DRIVER_LABELS[key]

    mapping = {
        "module_name": "Nhóm nghiệp vụ",
        "feature_name": "Chức năng",
        "requirement_name": "Yêu cầu cụ thể",
        "description": "Mô tả",
        "remarks": "Ghi chú",
        "candidate_price_codes": "Mã giá gợi ý",
        "mapping_confidence": "Độ chắc chắn khi ghép",
        "priority": "Mức ưu tiên",
        "complexity": "Độ phức tạp",
        "quantity": "Số lượng",
        "unit": "Đơn vị",
        "item_id": "Mã hạng mục",
        "source_table_id": "Bảng nguồn",
        "source_row_numbers": "Dòng nguồn",
    }
    if key in mapping:
        return mapping[key]
    return key.replace("_", " ").strip().capitalize()


def _render_text(value: Any, empty: str = "-") -> str:
    if _is_empty(value):
        return empty

    if isinstance(value, (list, tuple, set)):
        parts = [_render_text(x, empty="") for x in value]
        parts = [x for x in parts if x]
        return ", ".join(parts) if parts else empty

    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            rendered = _render_text(item, empty="")
            if rendered:
                parts.append(f"{_humanize_key(str(key))}: {rendered}")
        return "; ".join(parts) if parts else empty

    return str(value).strip() or empty


def _render_level(value: Any) -> str:
    key = str(value or "").strip().lower()
    return _LEVEL_LABELS.get(key, _render_text(value, empty="Chưa rõ"))


def _render_source_ref(table_id: Any, row_numbers: Any) -> str:
    table_text = _render_text(table_id, empty="")
    rows = row_numbers if isinstance(row_numbers, list) else []
    rows_text = ", ".join(str(x).strip() for x in rows if not _is_empty(x))

    if table_text and rows_text:
        return f"{table_text} - dòng {rows_text}"
    if table_text:
        return table_text
    if rows_text:
        return f"Dòng {rows_text}"
    return "-"


def _pick_first(item: Dict[str, Any], keys: List[str]) -> str:
    for key in keys:
        rendered = _render_text(item.get(key), empty="")
        if rendered:
            return rendered
    return ""


def _build_ba_summary_text(ba_analysis: Dict[str, Any]) -> str:
    summary_doc = ba_analysis.get("document_summary") or {}
    scope_items = ba_analysis.get("scope_items") or []
    assumptions = ba_analysis.get("assumptions") or []
    exclusions = ba_analysis.get("exclusions") or []
    unmapped = ba_analysis.get("unmapped_or_ambiguous_items") or []

    project_name = _render_text(summary_doc.get("project_name"), empty="")
    solution_type = _render_text(summary_doc.get("solution_type"), empty="")

    lead = f"Đã tách được {len(scope_items)} hạng mục chính"
    if project_name:
        lead += f" cho dự án {project_name}"
    lead += "."

    details: List[str] = []
    if solution_type:
        details.append(f"Loại giải pháp: {solution_type}.")
    if assumptions:
        details.append(f"Có {len(assumptions)} giả định cần lưu ý.")
    if exclusions:
        details.append(f"Có {len(exclusions)} hạng mục ngoài phạm vi.")
    if unmapped:
        details.append(f"Có {len(unmapped)} nội dung cần xác nhận thêm.")

    return " ".join([lead] + details).strip()


def build_ba_analysis_presentation(ba_analysis: Dict[str, Any]) -> Dict[str, Any]:
    summary_doc = ba_analysis.get("document_summary") or {}
    scope_items = ba_analysis.get("scope_items") or []
    assumptions = ba_analysis.get("assumptions") or []
    exclusions = ba_analysis.get("exclusions") or []
    drivers = ba_analysis.get("commercial_drivers") or {}
    unmapped = ba_analysis.get("unmapped_or_ambiguous_items") or []

    overview = {
        "summary_text": _build_ba_summary_text(ba_analysis),
        "facts": [
            {"label": "Hạng mục chính", "value": len(scope_items)},
            {"label": "Giả định", "value": len(assumptions)},
            {"label": "Ngoài phạm vi", "value": len(exclusions)},
            {"label": "Cần làm rõ", "value": len(unmapped)},
        ],
        "document_info": [
            {"label": "Tên dự án", "value": _render_text(summary_doc.get("project_name"), empty="Chưa có")},
            {"label": "Khách hàng", "value": _render_text(summary_doc.get("customer_name"), empty="Chưa có")},
            {"label": "Lĩnh vực", "value": _render_text(summary_doc.get("domain"), empty="Chưa có")},
            {"label": "Loại giải pháp", "value": _render_text(summary_doc.get("solution_type"), empty="Chưa có")},
            {"label": "Sheet đang dùng", "value": _render_text(summary_doc.get("sheet_name"), empty="Chưa có")},
        ],
    }

    scope_rows = []
    for idx, item in enumerate(scope_items, start=1):
        feature_name = _render_text(item.get("feature_name"), empty="")
        requirement_name = _render_text(item.get("requirement_name"), empty="")
        description = _render_text(item.get("description"), empty="")
        remarks = _render_text(item.get("remarks"), empty="")

        scope_rows.append({
            "STT": idx,
            "Nhóm nghiệp vụ": _render_text(item.get("module_name"), empty="Chưa rõ"),
            "Chức năng": feature_name or requirement_name or "Chưa rõ",
            "Yêu cầu cụ thể": requirement_name or feature_name or "Chưa rõ",
            "Mô tả dễ hiểu": description or remarks or "Chưa có mô tả",
            "Số lượng": item.get("quantity") if item.get("quantity") is not None else "-",
            "Đơn vị": _render_text(item.get("unit"), empty="-"),
            "Độ phức tạp": _render_level(item.get("complexity")),
            "Mức ưu tiên": _render_level(item.get("priority")),
            "Ghi chú": remarks or "-",
            "Tham chiếu": _render_source_ref(
                item.get("source_table_id"),
                item.get("source_row_numbers"),
            ),
        })

    driver_rows = []
    for key, label in _DRIVER_LABELS.items():
        rendered = _render_text(drivers.get(key), empty="")
        if rendered:
            driver_rows.append({"Yếu tố ảnh hưởng báo giá": label, "Giá trị": rendered})

    for key, value in drivers.items():
        if key in _DRIVER_LABELS:
            continue
        rendered = _render_text(value, empty="")
        if rendered:
            driver_rows.append({
                "Yếu tố ảnh hưởng báo giá": _humanize_key(str(key)),
                "Giá trị": rendered,
            })

    assumption_items = [
        _render_text(item.get("text"), empty="")
        for item in assumptions
        if _render_text(item.get("text"), empty="")
    ]

    exclusion_items = [
        _render_text(item.get("text"), empty="")
        for item in exclusions
        if _render_text(item.get("text"), empty="")
    ]

    review_rows = []
    for idx, item in enumerate(unmapped, start=1):
        if isinstance(item, str):
            review_rows.append({
                "STT": idx,
                "Nội dung cần làm rõ": item.strip() or "Nội dung cần xem lại",
                "Lý do hoặc ghi chú": "Cần xác nhận thêm từ tài liệu gốc.",
                "Tham chiếu": "-",
            })
            continue

        if not isinstance(item, dict):
            review_rows.append({
                "STT": idx,
                "Nội dung cần làm rõ": _render_text(item, empty="Nội dung cần xem lại"),
                "Lý do hoặc ghi chú": "Cần xác nhận thêm từ tài liệu gốc.",
                "Tham chiếu": "-",
            })
            continue

        main_text = _pick_first(item, _REVIEW_TEXT_KEYS) or "Nội dung cần xem lại"
        reason_text = _pick_first(item, list(_REVIEW_DETAIL_KEYS))

        extra_bits = []
        for key, value in item.items():
            if key in _SOURCE_KEYS or key in _REVIEW_DETAIL_KEYS or key in _REVIEW_TEXT_KEYS:
                continue
            rendered = _render_text(value, empty="")
            if rendered:
                extra_bits.append(f"{_humanize_key(str(key))}: {rendered}")

        details = reason_text
        if extra_bits:
            extra_text = "; ".join(extra_bits)
            details = f"{details}. {extra_text}".strip(". ") if details else extra_text
        if not details:
            details = "Cần xác nhận thêm từ tài liệu gốc."

        source_rows = item.get("source_row_numbers") or item.get("row_numbers") or item.get("rows") or item.get("source_rows") or []
        review_rows.append({
            "STT": idx,
            "Nội dung cần làm rõ": main_text,
            "Lý do hoặc ghi chú": details,
            "Tham chiếu": _render_source_ref(item.get("source_table_id"), source_rows),
        })

    return {
        "overview": overview,
        "scope_rows": scope_rows,
        "commercial_driver_rows": driver_rows,
        "assumption_items": assumption_items,
        "exclusion_items": exclusion_items,
        "review_rows": review_rows,
    }


def run_ba_detection(
    *,
    file_id: str,
    model: str,
    manifest_json: str,
    previous_response_id: Optional[str] = None,
) -> Dict[str, Any]:
    raw_text, response_id = ask_ci_ba_detection(
        file_id=file_id,
        model=model,
        previous_response_id=previous_response_id,
        manifest_json=manifest_json,
    )
    obj = parse_json_object(raw_text)
    result = BADetectionResult(**obj)
    return {
        "result": result.model_dump(),
        "response_id": response_id,
        "raw_text": raw_text,
    }


def run_ba_analysis(
    *,
    file_id: str,
    model: str,
    manifest_json: str,
    ba_detection: Dict[str, Any],
    previous_response_id: Optional[str] = None,
) -> Dict[str, Any]:
    raw_text, response_id = ask_ci_ba_analysis(
        file_id=file_id,
        model=model,
        previous_response_id=previous_response_id,
        manifest_json=manifest_json,
        ba_detection_json=json.dumps(ba_detection, ensure_ascii=False),
    )

    if not str(raw_text).strip():
        raise RuntimeError(
            "AI trả về phản hồi rỗng (Empty Response) cho bước BA Analysis. "
            "Điều này thường xảy ra khi file không đủ dữ liệu nghiệp vụ nhưng vẫn bị đẩy vào luồng BA."
        )

    try:
        obj = parse_json_object(raw_text)
    except Exception:
        raise RuntimeError(
            "Lỗi đọc JSON từ model AI. Dữ liệu trả về không đúng định dạng JSON. "
            f"RAW TEXT: {raw_text[:200]}..."
        )

    result = BAAnalysisResult(**obj)
    result_dict = result.model_dump()
    result_dict["presentation"] = build_ba_analysis_presentation(result_dict)
    return {
        "result": result_dict,
        "response_id": response_id,
        "raw_text": raw_text,
    }


def build_quotation_render_json(
    ba_analysis: Dict[str, Any],
    customer_name: str = "",
    quotation_no: str = "",
    currency: str = "VND",
) -> Dict[str, Any]:
    scope_items = ba_analysis.get("scope_items") or []
    assumptions = ba_analysis.get("assumptions") or []
    exclusions = ba_analysis.get("exclusions") or []
    summary_doc = ba_analysis.get("document_summary") or {}

    line_items = []
    for idx, item in enumerate(scope_items, start=1):
        qty = item.get("quantity") or 0
        line_items.append({
            "line_no": idx,
            "group_name": item.get("module_name") or "",
            "item_code": (item.get("candidate_price_codes") or [""])[0],
            "item_name": item.get("feature_name") or item.get("requirement_name") or item.get("module_name") or f"Hạng mục {idx}",
            "description": item.get("description") or "",
            "unit": item.get("unit") or "",
            "quantity": qty,
            "unit_price": 0,
            "amount": 0,
            "source_refs": [{
                "table_id": item.get("source_table_id", ""),
                "row_numbers": item.get("source_row_numbers") or [],
            }],
            "notes": item.get("remarks") or "",
        })

    out = QuotationRenderResult(
        quotation_meta={
            "quotation_no": quotation_no,
            "quotation_date": "",
            "currency": currency,
            "customer_name": customer_name,
            "project_name": summary_doc.get("project_name", ""),
            "validity_days": 30,
            "prepared_by": "",
        },
        header_fields={
            "customer_name": customer_name,
            "project_name": summary_doc.get("project_name", ""),
            "subject": f"Báo giá {summary_doc.get('solution_type', 'giải pháp')}".strip(),
        },
        line_items=line_items,
        summary={
            "subtotal": 0,
            "discount_amount": 0,
            "tax_rate": 0.1,
            "tax_amount": 0,
            "grand_total": 0,
        },
        assumptions_section=[x.get("text", "") for x in assumptions if x.get("text")],
        exclusions_section=[x.get("text", "") for x in exclusions if x.get("text")],
        internal_notes=ba_analysis.get("unmapped_or_ambiguous_items") or [],
        template_binding={
            "template_code": "quotation_v1",
            "sheet_name": "Quotation",
            "start_row_line_items": 15,
        },
    )
    return out.model_dump()
