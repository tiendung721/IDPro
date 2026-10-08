from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class BADetectionSheetCandidate(BaseModel):
    sheet_name: str
    score: float = 0.0
    scope_table_ids: List[str] = Field(default_factory=list)
    assumption_table_ids: List[str] = Field(default_factory=list)
    driver_table_ids: List[str] = Field(default_factory=list)


class BADetectionResult(BaseModel):
    document_type: str = "unknown"
    confidence: float = 0.0
    is_ba: bool = False
    sheet_candidates: List[BADetectionSheetCandidate] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)
    needs_user_confirmation: bool = True


class BAScopeItem(BaseModel):
    item_id: str
    source_table_id: str
    source_row_numbers: List[int] = Field(default_factory=list)
    module_name: Optional[str] = ""
    feature_name: Optional[str] = ""
    requirement_name: Optional[str] = ""
    description: Optional[str] = ""
    quantity: Optional[float] = None
    unit: Optional[str] = ""
    complexity: Optional[str] = "unknown"
    priority: Optional[str] = "unknown"
    remarks: Optional[str] = ""
    normalized_tags: List[str] = Field(default_factory=list)
    candidate_price_codes: List[str] = Field(default_factory=list)
    mapping_confidence: float = 0.0


class BAStatement(BaseModel):
    text: str
    source_table_id: str = ""
    source_row_numbers: List[int] = Field(default_factory=list)


class BAAnalysisResult(BaseModel):
    version: str = "1.0"
    document_summary: Dict[str, Any] = Field(default_factory=dict)
    scope_items: List[BAScopeItem] = Field(default_factory=list)
    commercial_drivers: Dict[str, Any] = Field(default_factory=dict)
    assumptions: List[BAStatement] = Field(default_factory=list)
    exclusions: List[BAStatement] = Field(default_factory=list)
    data_quality_flags: List[Dict[str, Any]] = Field(default_factory=list)
    unmapped_or_ambiguous_items: List[Dict[str, Any]] = Field(default_factory=list)

    @field_validator("assumptions", "exclusions", mode="before")
    @classmethod
    def parse_statements(cls, v):
        if not isinstance(v, list):
            return []
        out = []
        for x in v:
            if isinstance(x, str):
                out.append({"text": x})
            elif isinstance(x, dict):
                out.append(x)
        return out


class QuotationLineItem(BaseModel):
    line_no: int
    group_name: str = ""
    item_code: str = ""
    item_name: str = ""
    description: str = ""
    unit: str = ""
    quantity: float = 0
    unit_price: float = 0
    amount: float = 0
    source_refs: List[Dict[str, Any]] = Field(default_factory=list)
    notes: str = ""


class QuotationRenderResult(BaseModel):
    version: str = "1.0"
    quotation_meta: Dict[str, Any] = Field(default_factory=dict)
    header_fields: Dict[str, Any] = Field(default_factory=dict)
    line_items: List[QuotationLineItem] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)
    assumptions_section: List[str] = Field(default_factory=list)
    exclusions_section: List[str] = Field(default_factory=list)
    internal_notes: List[Dict[str, Any]] = Field(default_factory=list)
    template_binding: Dict[str, Any] = Field(default_factory=dict)