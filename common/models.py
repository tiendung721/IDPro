from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, model_validator


class Section(BaseModel):
    start_row: int
    end_row: int
    header_row: int
    start_col: Optional[int] = None
    end_col: Optional[int] = None
    label: Optional[str] = None


class SessionData(BaseModel):
    session_id: str
    file_path: str

    user_id: Optional[str] = None
    role: Optional[str] = None
    used_rule: Optional[bool] = False

    auto_sections: List[Section] = Field(default_factory=list)
    confirmed_sections: List[Section] = Field(default_factory=list)

    confirming: Optional[bool] = False
    confirmed: Optional[bool] = False
    rule_version: Optional[str] = None
    fingerprint: Optional[str] = None
    file_hash: Optional[str] = None

    owner_key: Optional[str] = None
    owner_user_id: Optional[str] = None

    is_known: Optional[bool] = False
    matched_fingerprint: Optional[str] = None
    matched_template_owner: Optional[str] = None

    session_overrides: Dict[str, Any] = Field(default_factory=dict)
    normalized_xlsx_path: Optional[str] = None
    openai_file_id: Optional[str] = None

    final_prev_response_id: Optional[str] = None
    final_spec_prev_response_id: Optional[str] = None

    # -------- QA continuity --------
    qa_prev_response_id: Optional[str] = None
    qa_thread_turn_count: int = 0
    qa_memory_summary: Optional[str] = None
    qa_recent_turns: List[Dict[str, str]] = Field(default_factory=list)

    sections_manifest_path: Optional[str] = None
    confirmed_sheet_name: Optional[str] = None
    manifest_hash: Optional[str] = None
    dataset_profile_compact: Optional[Dict[str, Any]] = None

    # -------- Report planning --------
    report_plan: Optional[Dict[str, Any]] = None
    report_plan_compact: Optional[Dict[str, Any]] = None
    report_plan_cache_key: Optional[str] = None
    report_plan_similarity_key: Optional[str] = None
    report_plan_version: Optional[str] = None
    report_catalog_version: Optional[str] = None

    # -------- Report selection & generate --------
    selected_reports: Optional[Dict[str, Any]] = None
    generated_dashboard_spec: Optional[Dict[str, Any]] = None
    generated_dashboard_summary: Optional[Dict[str, Any]] = None
    report_generation_context_key: Optional[str] = None
    report_generation_version: Optional[str] = None
    generate_prev_response_id: Optional[str] = None

    ba_detection: Optional[Dict[str, Any]] = None
    ba_analysis: Optional[Dict[str, Any]] = None
    quotation_preview: Optional[Dict[str, Any]] = None
    quotation_output_path: Optional[str] = None
    quotation_output_filename: Optional[str] = None

    document_flow: Optional[str] = None   # "ba" | "analytics" | None
    document_type: Optional[str] = None   # "ba_excel" | "non_ba" | "unknown"
    ba_detect_result: Optional[Dict[str, Any]] = None
    ba_analysis_result: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def _sync_owner_fields(self):
        try:
            ok = self.owner_key
            ou = self.owner_user_id

            if ((not ok) and isinstance(ou, str) and (ou.startswith("user:") or ou.startswith("admin:"))):
                self.owner_key = ou

            if self.owner_key and (not self.owner_user_id):
                self.owner_user_id = self.owner_key
        except Exception:
            pass
        return self