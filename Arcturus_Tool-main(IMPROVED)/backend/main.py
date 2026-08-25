import os
import re
import uuid
import uvicorn
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, field_validator
import httpx
from bs4 import BeautifulSoup

from .database import engine, get_db, Base, SessionLocal
from .auth_models import User
from .job_models import Job
import json
from io import BytesIO
import pandas as pd
from .auth import (
    get_password_hash, verify_password, create_access_token,
    get_current_user
)
from .services.ai_enricher import enrich_all_features
from .services.excel_generator import generate_excel
from .services.ppt_generator import generate_ppt
from .services.test_script_mapper import map_all_features_to_test_scripts
from .services.test_script_excel import generate_test_script_excel

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="OQUAT Intelligence Platform")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
os.makedirs("outputs", exist_ok=True)
app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")

# ============================================================================
# AUTH ENDPOINTS
# ============================================================================

class SignupRequest(BaseModel):
    email: str
    password: str
    full_name: str
    company: Optional[str] = None

class LoginRequest(BaseModel):
    email: str
    password: str

@app.post("/auth/signup")
def signup(request: SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == request.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed = get_password_hash(request.password)
    user = User(
        email=request.email,
        hashed_password=hashed,
        full_name=request.full_name,
        company=request.company
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    token = create_access_token({"sub": user.email})
    return {
        "access_token": token, 
        "token_type": "bearer", 
        "user": {"email": user.email, "full_name": user.full_name}
    }

@app.post("/auth/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_access_token({"sub": user.email})
    return {
        "access_token": token, 
        "token_type": "bearer", 
        "user": {"email": user.email, "full_name": user.full_name}
    }

@app.get("/auth/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {"email": current_user.email, "full_name": current_user.full_name}

# ============================================================================
# SCRAPE ENDPOINT (for website)
# ============================================================================

def _clean_incoming_url(value: Any) -> str:
    """
    Normalize a URL arriving from the React app or the extension.

    BUGFIX: /scrape called `request.url.strip()` internally but /extract
    compared `request.url` raw. A URL pasted with surrounding whitespace or an
    invisible character (zero-width space, BOM, non-breaking space — all common
    when copying out of a browser address bar or a document) therefore passed
    /scrape with 200 and was rejected by /extract with
    400 "Invalid Oracle URL". Normalizing at the model layer means every
    endpoint sees the same cleaned value.
    """
    text = str(value or "")
    # Strip zero-width space, zero-width non-joiner/joiner, BOM, and NBSP.
    text = re.sub(r"[\u200b\u200c\u200d\ufeff\u00a0]", "", text)
    return text.strip()


class ScrapeRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def _normalize_url(cls, v: str) -> str:
        return _clean_incoming_url(v)

from urllib.parse import urljoin


def extract_release_from_url(page_url: str) -> str:
    """
    Oracle readiness URLs always carry the release in the path, e.g.
    .../readiness/scm/26b/inv26b/26B-inventory-wn-t73741.htm  ->  26B
    This is the authoritative source; page-text scanning is only a fallback.
    """
    match = re.search(r"/(\d{2}[a-dA-D])(?:/|$)", page_url)
    return match.group(1).upper() if match else ""


def get_feature_prefix(module: str) -> str:
    """Generate feature prefix based on module name."""
    module_lower = str(module or "").lower()
    
    if any(x in module_lower for x in ["procure", "sourc", "purch", "contract"]):
        return "PRC"
    if any(x in module_lower for x in ["message", "b2b", "collaboration"]):
        return "MSG"
    if any(x in module_lower for x in ["order", "fulfill"]):
        return "ORM"
    if any(x in module_lower for x in ["manufactur", "production"]):
        return "MFG"
    if any(x in module_lower for x in ["supply chain", "planning"]):
        return "SCP"
    if any(x in module_lower for x in ["product hub", "product information"]):
        return "PIM"
    if any(x in module_lower for x in ["cost", "financial"]):
        return "CST"
    if any(x in module_lower for x in ["warehouse", "inventory", "logistics"]):
        return "INV"
    return "INV"

@app.post("/scrape")
async def scrape_oracle_page(request: ScrapeRequest):
    url = request.url.strip()

    print("=" * 80)
    print("RAW URL :", repr(request.url))
    print("AFTER STRIP :", repr(url))
    print("=" * 80)
    if not url or not url.startswith("https://docs.oracle.com"):
        raise HTTPException(status_code=400, detail="Invalid Oracle URL")
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            print("=" * 80)
            print("URL RECEIVED:", repr(url))
            print("=" * 80)
            response = await client.get(url)
            response.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch page: {str(e)}")
    
    soup = BeautifulSoup(response.text, "html.parser")
    
    # ============================================================
    # 1. EXTRACT RELEASE VERSION & DATE FROM MAIN PAGE
    # ============================================================
    # An explicit <base href> changes how the browser resolves relative links,
    # so mirror that before resolving any feature URLs.
    base_tag = soup.find("base")
    base_href = urljoin(url, base_tag.get("href")) if (base_tag and base_tag.get("href")) else url

    release_version = extract_release_from_url(url) or "26A"
    release_date = "May 2026"

    for element in soup.find_all(["h1", "h2", "h3", "h4", "p", "div"]):
        text = element.get_text(strip=True)
        if "Release" in text and "26" in text:
            # Only fall back to page text if the URL did not carry the release.
            if not extract_release_from_url(url):
                version_match = re.search(r'26[A-Z]', text)
                if version_match:
                    release_version = version_match.group()
            date_match = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}', text)
            if date_match:
                release_date = date_match.group()
                break
    
    # ============================================================
    # 2. FIND THE FEATURE TABLE
    # ============================================================
    table = soup.find("table")
    if not table:
        raise HTTPException(status_code=400, detail="No feature table found on this page")
    
    features = []
    rows = table.find_all("tr")
    header_skipped = False
    
    for idx, row in enumerate(rows):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        
        module = cells[0].get_text(strip=True) if len(cells) > 0 else ""
        title_cell = cells[1] if len(cells) > 1 else None
        impact = cells[2].get_text(strip=True) if len(cells) > 2 else ""
        action_required = cells[3].get_text(strip=True) if len(cells) > 3 else ""
        
        # Skip header row
        if not header_skipped and (title_cell and title_cell.get_text(strip=True).lower() == "feature" or module.lower() == "feature"):
            header_skipped = True
            continue
        
        title = ""
        feature_url = ""
        if title_cell:
            title = title_cell.get_text(strip=True)
            link = title_cell.find("a")
            if link and link.get("href"):
                # Resolve relative hrefs exactly as the browser (and therefore
                # the extension's content script) does. urljoin correctly treats
                # the listing page as a FILE, not a directory:
                #   base .../inv26b/26B-inventory-wn-t73741.htm
                #   href 26B-inventory-wn-f49705.htm#inv26b-f49705
                #   ->   .../inv26b/26B-inventory-wn-f49705.htm#inv26b-f49705
                feature_url = urljoin(base_href, link.get("href"))

        if not title or len(title) < 3:
            continue

        # A row whose title cell carries no anchor is a section/spacer row, not
        # a feature. Previously these silently inherited the listing page URL.
        if not feature_url:
            continue
        
        # ============================================================
        # 3. FEATURE OBJECT CONSTRUCTION
        # ============================================================
        # NOTE: the detail page is deliberately NOT fetched here.
        # enrich_feature() in ai_enricher.py reads ONLY "title" and "url"
        # from this object and then overwrites description, business_benefit,
        # action_required, impact, mandatory, steps_to_enable,
        # access_requirements, notes, bug_ids and oracle_feature_id from its
        # own fetch_oracle_detail_text(url) call. Scraping the detail page a
        # second time here produced values that were always discarded, while
        # doubling the request volume against docs.oracle.com and risking the
        # throttling/timeouts that degrade the enrichment fetch that matters.
        # This mirrors the Extension, whose content script emits listing-level
        # data only.
        # ============================================================
        # 4. BUILD THE COMPLETE FEATURE OBJECT
        # ============================================================
        features.append({
            "release_version": release_version,
            "release_date": release_date,
            "module": module,
            "generated_feature_id": "",
            "oracle_feature_id": "",
            "title": title,
            "delivery_status": "Enabled",
            "action_required": action_required or "No Setup Required",
            "impact": impact or "NO BUSINESS IMPACT",
            "access_requirements": "",
            "bug_ids": "None",
            "description": title,
            "steps_to_enable": "No",
            "url": feature_url,
            "priority": "Medium",
            "notes": "Validate the setup and business impact in a lower environment before production rollout.",
            "business_benefit": ""  # Will be filled by AI
        })
    
    return {"features": features, "count": len(features)}

# ============================================================================
# FEATURE EXTRACTION ENDPOINT
# ============================================================================

class ExtractRequest(BaseModel):
    url: str
    limit: Optional[int] = 1000
    features: List[Dict[str, Any]]
    script_mappings: Optional[List[Dict[str, str]]] = []

    @field_validator("url")
    @classmethod
    def _normalize_url(cls, v: str) -> str:
        return _clean_incoming_url(v)

TASKS: Dict[str, Dict[str, Any]] = {}


def persist_task(job_id: str) -> None:
    """
    Write the current in-memory TASKS[job_id] dict to the DB. Called
    wherever TASKS[job_id] is created or updated. Best-effort: a persistence
    failure here must never break the in-memory pipeline that already works,
    so errors are logged and swallowed rather than raised.
    """
    if job_id not in TASKS:
        return
    try:
        db = SessionLocal()
        try:
            payload = json.dumps(TASKS[job_id], default=str)
            existing = db.query(Job).filter(Job.job_id == job_id).first()
            if existing:
                existing.data = payload
            else:
                db.add(Job(job_id=job_id, data=payload))
            db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"[JOB PERSIST ERROR] {job_id}: {e}")


def hydrate_task(job_id: str) -> bool:
    """
    If job_id isn't in the in-memory TASKS dict (e.g. after a backend
    restart), try loading it from the DB. Returns True if the job is now
    available in TASKS either way.
    """
    if job_id in TASKS:
        return True
    try:
        db = SessionLocal()
        try:
            row = db.query(Job).filter(Job.job_id == job_id).first()
            if row:
                TASKS[job_id] = json.loads(row.data)
                return True
        finally:
            db.close()
    except Exception as e:
        print(f"[JOB HYDRATE ERROR] {job_id}: {e}")
    return False

@app.post("/extract")
async def extract_features(
    request: ExtractRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # request.url is already normalized by ExtractRequest._normalize_url.
    url = request.url

    print("=" * 80)
    print("EXTRACT URL      :", repr(url))
    print("EXTRACT FEATURES :", len(request.features or []))
    print("=" * 80)

    if not url.startswith("https://docs.oracle.com"):
        # The rejected value is echoed back so a stray character is visible
        # in the browser instead of producing an opaque 400.
        raise HTTPException(
            status_code=400,
            detail=f"Invalid Oracle URL: {url!r}"
        )

    if not request.features:
        raise HTTPException(status_code=400, detail="No features provided")

    # Fail loudly on a malformed feature set rather than silently enriching
    # against wrong pages. /generate already did this; /extract (the path the
    # React app uses) did not, which is how the URL defect stayed invisible.


    try:
        validate_feature_urls(request.features)
    except HTTPException as e:
        print("=" * 80)
        print("FEATURE URL VALIDATION FAILED")
        print(e.detail)
        print("=" * 80)
        raise

    job_id = str(uuid.uuid4())

    # Store in TASKS dictionary
    TASKS[job_id] = {
        "task_id": job_id,
        "status": "Queued",
        "feature_count": len(request.features),
        "processed": 0,
        "current_feature": None,
        "excel_url": None,
        "ppt_url": None,
        "error": None,
        "features": [],
        "script_mappings": request.script_mappings or []
    }

    persist_task(job_id)

    # Start background processing
    background_tasks.add_task(
        run_background_pipeline,
        job_id,
        request.features[:request.limit],
        request.limit or 1000,
        url,
        request.script_mappings or [],
    )

    return {
        "job_id": job_id,
        "status_url": f"/status/{job_id}"
    }
# ============================================================================
# YOUR EXISTING ENDPOINTS (UNCHANGED)
# ============================================================================

class GenerateRequest(BaseModel):
    url: str
    limit: Optional[int] = Field(default=1000)
    injected_features: List[Dict[str, Any]]
    script_mappings: Optional[List[Dict[str, str]]] = Field(default=[])

    @field_validator("url")
    @classmethod
    def _normalize_url(cls, v: str) -> str:
        return _clean_incoming_url(v)

def output_slug_from_url(url: str) -> str:
    parts = url.rstrip("/").split("/")
    target = parts[-2] if parts[-1] == "index.html" else parts[-1]
    return target.replace(".html", "").replace(".htm", "") or "oracle_report"

def validate_feature_urls(features: List[Dict[str, Any]]) -> None:
    missing = []
    invalid = []
    for idx, feature in enumerate(features, start=1):
        title = str(feature.get("title") or feature.get("name") or f"Feature #{idx}").strip()
        url = str(feature.get("url") or feature.get("source_url") or "").strip()
        if not url:
            missing.append(title)
        elif not url.startswith("https://docs.oracle.com"):
            invalid.append({"title": title, "url": url})
    if missing:
        raise HTTPException(status_code=400, detail={
            "message": "Some injected features are missing individual Oracle feature URLs.",
            "missing_count": len(missing),
            "examples": missing[:5],
        })
    if invalid:
        raise HTTPException(status_code=400, detail={
            "message": "Some feature URLs are invalid.",
            "invalid_count": len(invalid),
            "examples": invalid[:5],
        })
async def run_background_pipeline(task_id: str, raw_features: list, limit: int, url: str, mappings: list):
    try:
        print("=" * 80)
        print("BACKGROUND PIPELINE STARTED")
        print("Task ID:", task_id)
        print("Total Features:", len(raw_features))
        print("=" * 80)

        TASKS[task_id].update({"status": "Enriching", "error": None})
        persist_task(task_id)

        features_to_process = raw_features[:limit] if limit and limit > 0 else raw_features

        print("Starting AI enrichment...")

        enriched_features = await enrich_all_features(
            features_to_process,
            task_status=TASKS[task_id],
        )

        print("AI enrichment completed.")
        print("Features enriched:", len(enriched_features))

        TASKS[task_id]["features"] = enriched_features
        TASKS[task_id]["script_mappings"] = mappings
        TASKS[task_id]["status"] = "Generating Files"
        persist_task(task_id)

        slug = output_slug_from_url(url)
        excel_path = f"outputs/oracle_{slug}.xlsx"
        ppt_path = f"outputs/oracle_{slug}.pptx"

        print("Generating Excel...")
        generate_excel(enriched_features, excel_path)

        print("Generating PowerPoint...")
        generate_ppt(enriched_features, ppt_path)

        TASKS[task_id].update({
            "status": "Completed",
            "feature_count": len(enriched_features),
            "processed": len(enriched_features),
            "current_feature": None,
            "excel_url": f"/outputs/oracle_{slug}.xlsx",
            "ppt_url": f"/outputs/oracle_{slug}.pptx",
            "error": None,
        })

        persist_task(task_id)

    except Exception as e:
        import traceback

        print("=" * 80)
        print("BACKGROUND PIPELINE FAILED")
        traceback.print_exc()
        print("=" * 80)

        TASKS[task_id].update({
            "status": "Failed",
            "error": str(e)
        })

        persist_task(task_id)

@app.post("/generate")
async def generate_report_endpoint(request: GenerateRequest, background_tasks: BackgroundTasks):
    if not request.url.startswith("https://docs.oracle.com"):
        raise HTTPException(status_code=400, detail="Invalid URL.")
    if not request.injected_features:
        raise HTTPException(status_code=400, detail="Missing extension data payloads.")
    validate_feature_urls(request.injected_features)

    task_id = str(uuid.uuid4())
    TASKS[task_id] = {
        "task_id": task_id,
        "status": "Queued",
        "feature_count": len(request.injected_features),
        "processed": 0,
        "current_feature": None,
        "excel_url": None,
        "ppt_url": None,
        "error": None,
        "features": [],
        "script_mappings": request.script_mappings or []
    }
    persist_task(task_id)
    background_tasks.add_task(
        run_background_pipeline,
        task_id,
        request.injected_features,
        request.limit or 1000,
        request.url,
        request.script_mappings or [],
    )
    return {
        "message": "Pipeline started successfully.",
        "task_id": task_id,
        "status_url": f"/status/{task_id}",
    }

@app.get("/status/{task_id}")
def get_pipeline_status(task_id: str):
    if not hydrate_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found.")
    return TASKS[task_id]

@app.get("/status")
def get_latest_status():
    if not TASKS:
        return {"status": "Idle", "feature_count": 0, "processed": 0, "error": None}
    latest_task_id = list(TASKS.keys())[-1]
    return TASKS[latest_task_id]

def _parse_test_script_mapping_file(contents: bytes) -> List[Dict[str, str]]:
    """Parse the HR test-script mapping workbook used by the extension workflow."""
    try:
        frame = pd.read_excel(BytesIO(contents), sheet_name=0)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unable to read the test-script mapping Excel file: {exc}",
        )

    normalized = {
        re.sub(r"\s+", " ", str(col)).strip().lower(): col
        for col in frame.columns
    }

    script_number_col = None
    script_name_col = None

    for key, original in normalized.items():
        compact = key.replace(" ", "")
        if compact == "scriptnumber":
            script_number_col = original
        elif compact in {"scriptname/scenarios", "scriptname/scenario", "scriptname"}:
            script_name_col = original

    if script_number_col is None or script_name_col is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid mapping workbook. Required columns are "
                "'Script Number' and 'Script Name/ Scenarios'."
            ),
        )

    mappings = []
    for _, row in frame.iterrows():
        script_number = str(row.get(script_number_col, "")).strip()
        script_name = str(row.get(script_name_col, "")).strip()

        if script_number.lower() in {"", "nan", "none"}:
            continue
        if script_name.lower() in {"", "nan", "none"}:
            continue

        mappings.append({
            "script_number": script_number,
            "script_name": script_name,
        })

    if not mappings:
        raise HTTPException(
            status_code=400,
            detail="The mapping workbook does not contain any script mappings.",
        )

    return mappings


@app.post("/generate-test-scripts/{task_id}")
async def generate_test_scripts_endpoint(
    task_id: str,
    mapping_file: Optional[UploadFile] = File(default=None),
):
    if not hydrate_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found.")

    features = TASKS[task_id].get("features", [])
    mappings = TASKS[task_id].get("script_mappings", [])

    if not features:
        raise HTTPException(status_code=404, detail="No enriched features found for this task.")

    # The HR workbook is supplied at test-script generation time. This avoids
    # changing the existing Excel/PPT extraction pipeline and lets the same
    # generated feature set be mapped against the current HR script catalogue.
    if mapping_file is not None:
        contents = await mapping_file.read()
        mappings = _parse_test_script_mapping_file(contents)

    if not mappings:
        raise HTTPException(
            status_code=400,
            detail="Please upload the HR test-script mapping Excel file before generating scripts.",
        )

    test_script_data = map_all_features_to_test_scripts(features, mappings)

    output_filename = f"outputs/UAT_Test_Scripts_{task_id}.xlsx"
    file_path = generate_test_script_excel(test_script_data, output_path=output_filename)

    return FileResponse(
        path=file_path,
        filename="OQUAT_UAT_Test_Scripts.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

@app.get("/")
def health_check():
    return {"status": "Active", "engine": "OQUAT Extension Pipeline Ready"}

@app.get("/health")
def health_check_detailed():
    return {"status": "healthy", "database": "connected"}

# At the bottom of your main.py
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port)
