from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import os

from dotenv import load_dotenv
load_dotenv(override=True)


from controllers.extractor_controller import router as extractor_router
from controllers.section_confirm_controller import router as confirm_router
from controllers.sections_controller import router as sections_router
from controllers.qa_controller import router as qa_router
from controllers.auth_controller import router as auth_router
from controllers.template_controller import router as template_router
from controllers.user_login_controller import router as user_login_router
from controllers.admin_users_controller import router as admin_users_router
from controllers.report_plan_controller import router as report_plan_router
from controllers.generate_report_controller import router as generate_report_router
from controllers.ba_detect_controller import router as ba_detect_router
from controllers.ba_analysis_controller import router as ba_analysis_router
from controllers.quotation_generate_controller import router as quotation_generate_router
from controllers.post_confirm_router_controller import router as post_confirm_router

try:
    from controllers.history_controller import router as history_router
except Exception:
    history_router = None

APP_NAME = "AI Agent Backend"
APP_DESC = "API cho phép người dùng tương tác với AI Agent để xử lý dữ liệu, xác nhận cấu trúc bảng, xuất báo cáo, hỏi đáp trên dữ liệu."
APP_VER = "2.0.0"

app = FastAPI(title=APP_NAME, description=APP_DESC, version=APP_VER)


ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8501",
    "http://127.0.0.1:8501",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):(5173|8501)",
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],
)


OUTPUT_DIR = os.getenv("OUTPUT_DIR", os.path.join(os.getcwd(), "output"))
os.makedirs(OUTPUT_DIR, exist_ok=True)          
app.mount("/static", StaticFiles(directory=OUTPUT_DIR), name="static")

@app.get("/health")
def health():
    return {"ok": True, "service": APP_NAME, "version": APP_VER}


@app.exception_handler(Exception)
async def unhandled_exc_handler(request: Request, exc: Exception):
    
    return JSONResponse(
        status_code=500,
        content={"ok": False, "code": "UNHANDLED_ERROR", "error": str(exc)},
    )

app.include_router(extractor_router, prefix="", tags=["extractor"])
app.include_router(sections_router, prefix="", tags=["sections"])
app.include_router(confirm_router,   prefix="", tags=["confirm"])
app.include_router(qa_router, tags=["qa"])
app.include_router(auth_router, tags=["auth"])
app.include_router(template_router, tags=["template"])
app.include_router(user_login_router, tags=["auth"])
app.include_router(admin_users_router)
app.include_router(report_plan_router, prefix="", tags=["report"])
app.include_router(generate_report_router, prefix="", tags=["report"])
app.include_router(ba_detect_router)
app.include_router(ba_analysis_router)
app.include_router(quotation_generate_router)
app.include_router(post_confirm_router)

if history_router is not None:
    app.include_router(history_router, prefix="", tags=["history"])


@app.get("/")
def index():
    endpoints = ["/upload", "/preview", "/confirm_sections", "/final", "/qa", "/health", "/static/<file>"]
    if history_router is not None:
        endpoints.extend(["/history/{user_id} (GET)", "/history/{user_id} (DELETE)"])
    return {
        "ok": True,
        "message": "AI Agent Backend is running.",
        "endpoints": endpoints
    }
