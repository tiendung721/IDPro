from __future__ import annotations

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, model_validator


class Section(BaseModel):
    start_row: int
    end_row: int
    header_row: int
    label: Optional[str] = None


class SessionData(BaseModel):
    session_id: str
    file_path: str

    # Legacy / informational 
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

    # Canonical ownership field:
    # - "user:<user_id>"  cho user (JWT USER, gồm cả guest JWT)
    # - "admin:<admin_id>" cho admin (JWT ADMIN)
    owner_key: Optional[str] = None


    # Legacy field (giữ để đọc dữ liệu cũ / tương thích tạm thời)
    owner_user_id: Optional[str] = None

    is_known: Optional[bool] = False
    matched_fingerprint: Optional[str] = None
    matched_template_owner: Optional[str] = None 

    session_overrides: Dict[str, Any] = Field(default_factory=dict)
    
    # Normalized workbook for CI (data-only: T1..Tn + __src_row__)
    normalized_xlsx_path: Optional[str] = None

    # OpenAI Files id for CI chat/report
    openai_file_id: Optional[str] = None

    final_prev_response_id: Optional[str] = None
    
    # For chat continuity
    qa_prev_response_id: Optional[str] = None
    
    sections_manifest_path: Optional[str] = None

    confirmed_sheet_name: Optional[str] = None


    @model_validator(mode="after")
    def _sync_owner_fields(self):
        """Giữ đồng bộ owner_key <-> owner_user_id để không làm vỡ dữ liệu cũ.
        - Nếu owner_key trống nhưng owner_user_id có dạng prefix hợp lệ => copy sang owner_key
        - Nếu owner_key có mà owner_user_id trống => copy ngược lại (legacy sync)
        """
        try:
            ok = self.owner_key
            ou = self.owner_user_id

            if (not ok) and isinstance(ou, str) and ou.startswith("user:") or ou.startswith("admin:"):
                self.owner_key = ou

            if self.owner_key and (not self.owner_user_id):
                self.owner_user_id = self.owner_key
        except Exception:
            pass
        return self
