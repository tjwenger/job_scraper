import logging
import re
from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()  # Must run before any module reads env vars
from fastapi import FastAPI, Request, Form, BackgroundTasks, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import database as db
from scheduler import run_scraper, run_all_scrapers, start_scheduler, stop_scheduler
from scrapers import ALL_SCRAPERS
import config

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

templates = Jinja2Templates(directory="templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Job Scraper", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    search: str = "",
    source: str = "",
    status: str = "",
    show_declined: bool = False,
    page: int = 1,
):
    per_page = 50
    offset = (page - 1) * per_page
    jobs = db.get_jobs(search=search, source=source, status=status, show_declined=show_declined, limit=per_page, offset=offset)
    total = db.count_jobs(search=search, source=source, status=status, show_declined=show_declined)
    sources = db.get_sources()
    scrape_log = db.get_scrape_log(10)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "jobs": jobs,
            "total": total,
            "page": page,
            "per_page": per_page,
            "search": search,
            "source": source,
            "status": status,
            "sources": sources,
            "scrape_log": scrape_log,
            "all_scrapers": list(ALL_SCRAPERS.keys()),
            "keywords": config.KEYWORDS,
            "show_declined": show_declined,
        },
    )


@app.post("/scrape")
async def trigger_scrape(
    background_tasks: BackgroundTasks,
    scraper: str = Form("all"),
    keywords: str = Form(""),
):
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()] or None

    if scraper == "all":
        background_tasks.add_task(run_all_scrapers, kw_list)
    else:
        background_tasks.add_task(run_scraper, scraper, kw_list)

    return RedirectResponse("/?scraping=1", status_code=303)


@app.post("/status/{job_id}")
async def set_status(job_id: str, status: str = Form(...)):
    db.update_status(job_id, status)
    return JSONResponse({"ok": True})


@app.post("/score-all")
async def trigger_score(background_tasks: BackgroundTasks):
    from scorer import score_unscored_jobs
    background_tasks.add_task(score_unscored_jobs)
    return RedirectResponse("/?scoring=1", status_code=303)


@app.post("/notes/{job_id}")
async def set_notes(job_id: str, notes: str = Form(...)):
    db.update_notes(job_id, notes)
    return JSONResponse({"ok": True})


@app.get("/rejections", response_class=HTMLResponse)
async def rejections(request: Request):
    notes = db.get_rejection_notes()
    return templates.TemplateResponse("rejections.html", {"request": request, "notes": notes})


@app.get("/api/jobs")
async def api_jobs(search: str = "", source: str = "", status: str = "", limit: int = 100):
    return db.get_jobs(search=search, source=source, status=status, limit=limit)


@app.get("/api/log")
async def api_log():
    return db.get_scrape_log()


@app.get("/api/scrape-status")
async def scrape_status():
    """Returns whether a scrape is currently running and the total job count."""
    running = db.is_scrape_running()
    return {"running": running, "total": db.count_jobs()}


@app.post("/upload-resume")
async def upload_resume(file: UploadFile = File(...)):
    """Replace resume.txt with the uploaded .txt or .pdf file."""
    from pathlib import Path
    resume_path = Path(__file__).parent / "resume.txt"

    data = await file.read()
    filename = (file.filename or "").lower()

    if filename.endswith(".pdf"):
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    else:
        text = data.decode("utf-8", errors="replace").strip()

    if not text:
        return JSONResponse({"error": "Could not extract text from file."}, status_code=400)

    resume_path.write_text(text, encoding="utf-8")
    return JSONResponse({"ok": True, "chars": len(text)})


@app.post("/tailor/{job_id}")
async def tailor_job(job_id: str):
    """Call Claude to tailor resume.txt for the given job. Returns tailored text as JSON."""
    jobs = db.get_jobs(limit=1, offset=0)  # need a way to fetch by id
    job = db.get_job_by_id(job_id)
    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)
    try:
        from tailor import tailor_resume
        text = tailor_resume(
            title=job["title"],
            company=job["company"],
            description=job.get("description", ""),
        )
        return {"tailored": text}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/keywords")
async def get_keywords():
    return {"keywords": config.KEYWORDS, "exclude_keywords": config.EXCLUDE_KEYWORDS}


@app.post("/api/keywords")
async def save_keywords(request: Request):
    body = await request.json()
    kw = [k.strip() for k in body.get("keywords", []) if str(k).strip()]
    ex = [k.strip() for k in body.get("exclude_keywords", []) if str(k).strip()]
    config.save_keywords(kw, ex)
    config.reload()
    return {"ok": True, "keywords": config.KEYWORDS, "exclude_keywords": config.EXCLUDE_KEYWORDS}


@app.post("/download")
async def download_resume(
    content: str = Form(...),
    fmt: str = Form("docx"),
    filename: str = Form("tailored_resume"),
):
    """Generate and return a DOCX or PDF from the tailored resume text."""
    from tailor import generate_docx, generate_pdf
    from fastapi.responses import Response

    safe_name = re.sub(r"[^\w\-]", "_", filename)

    if fmt == "pdf":
        data = generate_pdf(content)
        return Response(
            content=data,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.pdf"'},
        )
    else:
        data = generate_docx(content)
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.docx"'},
        )
