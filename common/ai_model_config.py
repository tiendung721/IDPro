import os


def _pick(*names: str, default: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return default.strip()


def get_ba_detect_model() -> str:
    return _pick("BA_DETECT_MODEL", default="gpt-5.4-nano")


def get_ba_analysis_model() -> str:
    return _pick("BA_ANALYSIS_MODEL", default="gpt-5-mini")


def get_report_plan_model() -> str:
    return _pick("REPORT_PLAN_CI_MODEL", default="gpt-5-mini")


def get_qa_model() -> str:
    return _pick("QA_CI_MODEL", default="gpt-4.1-mini")


def get_dashboard_model() -> str:
    return _pick("DASHBOARD_CI_MODEL", default="gpt-5.4-mini")
