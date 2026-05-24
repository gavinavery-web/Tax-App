from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import RedirectResponse, StreamingResponse, Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import io
import logging
import csv
import uuid
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Annotated
from datetime import datetime, timezone

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="Tax Evidence Vault")
api_router = APIRouter(prefix="/api")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =================== Constants ===================
SINGLETON_KEY = "default"  # Single-user app

DRIVE_SCOPES = ['https://www.googleapis.com/auth/drive']

FOLDER_STRUCTURE = [
    ("01 ATO", "ATO"),
    ("02 PAYG Income", "PAYG Income"),
    ("03 Airbnb", "Airbnb"),
    ("04 Waggrakine Rental", "Waggrakine Rental"),
    ("05 Heathridge", "Heathridge"),
    ("06 Revive", "Revive"),
    ("07 Bank Statements", "Bank Statement"),
    ("08 Salary Packaging Maxxia", "Salary Packaging / Maxxia"),
    ("09 Accountant Review", "Accountant Review"),
    ("10 Missing Evidence", "Missing Evidence"),
    ("11 Final Accountant Pack", "Final Accountant Pack"),
]

# Category -> folder name mapping (used to decide which subfolder receives the file)
CATEGORY_TO_FOLDER = {
    "ATO": "01 ATO",
    "PAYG Income": "02 PAYG Income",
    "Airbnb": "03 Airbnb",
    "Waggrakine Rental": "04 Waggrakine Rental",
    "Heathridge": "05 Heathridge",
    "Revive": "06 Revive",
    "Bank Statement": "07 Bank Statements",
    "Salary Packaging / Maxxia": "08 Salary Packaging Maxxia",
    "Super / HECS": "02 PAYG Income",
    "Accountant Review": "09 Accountant Review",
    "Other": "10 Missing Evidence",
}

CATEGORIES = list(CATEGORY_TO_FOLDER.keys())
TAX_YEARS = ["FY2024", "FY2025", "Both", "Unsure"]
STATUS_OPTIONS = [
    "Uploaded only",
    "Needs analysis",
    "Analysed",
    "Missing evidence",
    "Accountant review",
    "Complete",
]
PRIORITIES = ["Critical", "Important", "Later"]

PAYG_PRELOAD = [
    {"tax_year": "FY2024", "employer": "St John Ambulance", "amount": 600},
    {"tax_year": "FY2024", "employer": "IPN Medical", "amount": 14198},
    {"tax_year": "FY2024", "employer": "Edith Cowan University", "amount": 12590},
    {"tax_year": "FY2025", "employer": "Edith Cowan University", "amount": 7511},
    {"tax_year": "FY2025", "employer": "St John Ambulance", "amount": 34992},
    {"tax_year": "FY2025", "employer": "Executive Risk Solutions", "amount": 33360},
]

MISSING_PRELOAD = [
    # Critical
    {"item_needed": "FY2024 Airbnb income evidence", "category": "Airbnb", "tax_year": "FY2024", "priority": "Critical", "where_to_find": "Airbnb host dashboard → Earnings → Annual report", "why_matters": "Required to declare rental income"},
    {"item_needed": "FY2025 Airbnb income evidence", "category": "Airbnb", "tax_year": "FY2025", "priority": "Critical", "where_to_find": "Airbnb host dashboard → Earnings → Annual report", "why_matters": "Required to declare rental income"},
    {"item_needed": "Heathridge mortgage interest statement FY2024", "category": "Heathridge", "tax_year": "FY2024", "priority": "Critical", "where_to_find": "Lender online banking → tax statements", "why_matters": "Deductible interest claim"},
    {"item_needed": "Heathridge mortgage interest statement FY2025", "category": "Heathridge", "tax_year": "FY2025", "priority": "Critical", "where_to_find": "Lender online banking → tax statements", "why_matters": "Deductible interest claim"},
    {"item_needed": "Waggrakine property management annual statement FY2024", "category": "Waggrakine Rental", "tax_year": "FY2024", "priority": "Critical", "where_to_find": "Property manager (request annual statement)", "why_matters": "Income & expense source"},
    {"item_needed": "Waggrakine property management annual statement FY2025", "category": "Waggrakine Rental", "tax_year": "FY2025", "priority": "Critical", "where_to_find": "Property manager (request annual statement)", "why_matters": "Income & expense source"},
    {"item_needed": "Waggrakine mortgage interest statement FY2024", "category": "Waggrakine Rental", "tax_year": "FY2024", "priority": "Critical", "where_to_find": "Lender online banking → tax statements", "why_matters": "Deductible interest claim"},
    {"item_needed": "Waggrakine mortgage interest statement FY2025", "category": "Waggrakine Rental", "tax_year": "FY2025", "priority": "Critical", "where_to_find": "Lender online banking → tax statements", "why_matters": "Deductible interest claim"},
    {"item_needed": "Revive financial statements FY2024", "category": "Revive", "tax_year": "FY2024", "priority": "Critical", "where_to_find": "Accountant or bookkeeping software (Xero/MYOB)", "why_matters": "Company tax return"},
    {"item_needed": "Revive financial statements FY2025", "category": "Revive", "tax_year": "FY2025", "priority": "Critical", "where_to_find": "Accountant or bookkeeping software (Xero/MYOB)", "why_matters": "Company tax return"},
    {"item_needed": "Maxxia annual summary FY2024", "category": "Salary Packaging / Maxxia", "tax_year": "FY2024", "priority": "Critical", "where_to_find": "Maxxia online portal → statements", "why_matters": "Salary packaging reportable amounts"},
    {"item_needed": "Maxxia annual summary FY2025", "category": "Salary Packaging / Maxxia", "tax_year": "FY2025", "priority": "Critical", "where_to_find": "Maxxia online portal → statements", "why_matters": "Salary packaging reportable amounts"},
    {"item_needed": "Personal bank statements FY2024", "category": "Bank Statement", "tax_year": "FY2024", "priority": "Critical", "where_to_find": "Internet banking → statements export", "why_matters": "Substantiate deductions & income"},
    {"item_needed": "Personal bank statements FY2025", "category": "Bank Statement", "tax_year": "FY2025", "priority": "Critical", "where_to_find": "Internet banking → statements export", "why_matters": "Substantiate deductions & income"},
    {"item_needed": "Revive bank statements FY2024", "category": "Bank Statement", "tax_year": "FY2024", "priority": "Critical", "where_to_find": "Business banking portal", "why_matters": "Company income & expense trail"},
    {"item_needed": "Revive bank statements FY2025", "category": "Bank Statement", "tax_year": "FY2025", "priority": "Critical", "where_to_find": "Business banking portal", "why_matters": "Company income & expense trail"},
    # Important
    {"item_needed": "Heathridge insurance", "category": "Heathridge", "tax_year": "Both", "priority": "Important", "where_to_find": "Insurer portal / renewal emails", "why_matters": "Deductible expense"},
    {"item_needed": "Waggrakine insurance", "category": "Waggrakine Rental", "tax_year": "Both", "priority": "Important", "where_to_find": "Insurer portal / renewal emails", "why_matters": "Deductible expense"},
    {"item_needed": "Council rates", "category": "Waggrakine Rental", "tax_year": "Both", "priority": "Important", "where_to_find": "Council portal / rates notices", "why_matters": "Deductible expense"},
    {"item_needed": "Water rates", "category": "Waggrakine Rental", "tax_year": "Both", "priority": "Important", "where_to_find": "Water utility portal", "why_matters": "Deductible expense"},
    {"item_needed": "Electricity", "category": "Other", "tax_year": "Both", "priority": "Important", "where_to_find": "Provider portal / bills", "why_matters": "Possible deduction (rental portion)"},
    {"item_needed": "Gas", "category": "Other", "tax_year": "Both", "priority": "Important", "where_to_find": "Provider portal / bills", "why_matters": "Possible deduction (rental portion)"},
    {"item_needed": "Internet", "category": "Other", "tax_year": "Both", "priority": "Important", "where_to_find": "Provider portal / bills", "why_matters": "Possible work-related deduction"},
    {"item_needed": "Cleaning receipts", "category": "Airbnb", "tax_year": "Both", "priority": "Important", "where_to_find": "Email receipts, bank statements", "why_matters": "Deductible expense for Airbnb"},
    {"item_needed": "Airbnb supplies", "category": "Airbnb", "tax_year": "Both", "priority": "Important", "where_to_find": "Store receipts / card statements", "why_matters": "Deductible expense for Airbnb"},
    # Later
    {"item_needed": "Phone bills", "category": "Other", "tax_year": "Both", "priority": "Later", "where_to_find": "Telco portal", "why_matters": "Possible work-use deduction"},
    {"item_needed": "Laundry", "category": "Other", "tax_year": "Both", "priority": "Later", "where_to_find": "Diary / estimate", "why_matters": "Uniform laundry deduction"},
    {"item_needed": "Uniforms", "category": "Other", "tax_year": "Both", "priority": "Later", "where_to_find": "Receipts", "why_matters": "Work-related clothing deduction"},
    {"item_needed": "CPD / training", "category": "Other", "tax_year": "Both", "priority": "Later", "where_to_find": "Course receipts / invoices", "why_matters": "Self-education deduction"},
    {"item_needed": "Small work deductions", "category": "Other", "tax_year": "Both", "priority": "Later", "where_to_find": "Receipts / bank statements", "why_matters": "Misc work deductions"},
]

# Dashboard cards
DASHBOARD_CARDS = [
    {"key": "fy2024", "title": "FY2024 Tax Return", "type": "tax_year", "value": "FY2024"},
    {"key": "fy2025", "title": "FY2025 Tax Return", "type": "tax_year", "value": "FY2025"},
    {"key": "ato", "title": "ATO Documents", "type": "category", "value": "ATO"},
    {"key": "airbnb", "title": "Airbnb", "type": "category", "value": "Airbnb"},
    {"key": "waggrakine", "title": "Waggrakine Rental", "type": "category", "value": "Waggrakine Rental"},
    {"key": "heathridge", "title": "Heathridge", "type": "category", "value": "Heathridge"},
    {"key": "revive", "title": "Revive", "type": "category", "value": "Revive"},
    {"key": "bank", "title": "Bank Statements", "type": "category", "value": "Bank Statement"},
    {"key": "review", "title": "Accountant Review Required", "type": "review", "value": True},
    {"key": "missing", "title": "Missing Documents", "type": "missing", "value": None},
]


# =================== Models ===================

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Document(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    file_type: str
    original_filename: str
    tax_year: str
    category: str
    notes: Optional[str] = ""
    accountant_review: str = "No"  # Yes / No / Unsure
    status: str = "Uploaded only"
    key_figures_found: Optional[str] = ""
    what_it_proves: Optional[str] = ""
    missing_followup: Optional[str] = ""
    drive_file_id: Optional[str] = None
    drive_link: Optional[str] = None
    drive_folder_id: Optional[str] = None
    drive_folder_name: Optional[str] = None
    size_bytes: int = 0
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class DocumentUpdate(BaseModel):
    name: Optional[str] = None
    tax_year: Optional[str] = None
    category: Optional[str] = None
    notes: Optional[str] = None
    accountant_review: Optional[str] = None
    status: Optional[str] = None
    key_figures_found: Optional[str] = None
    what_it_proves: Optional[str] = None
    missing_followup: Optional[str] = None


class Figure(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_id: Optional[str] = None
    figure_type: str  # income, tax_withheld, expense, interest, liability, other, payg_income
    amount: float
    description: Optional[str] = ""
    source_document: Optional[str] = ""
    tax_year: Optional[str] = ""
    category: Optional[str] = ""
    created_at: str = Field(default_factory=utc_now_iso)


class FigureCreate(BaseModel):
    figure_type: str
    amount: float
    description: Optional[str] = ""
    source_document: Optional[str] = ""
    tax_year: Optional[str] = ""
    category: Optional[str] = ""
    document_id: Optional[str] = None


class MissingItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    item_needed: str
    category: str
    tax_year: str
    priority: str
    where_to_find: Optional[str] = ""
    why_matters: Optional[str] = ""
    status: str = "Not started"  # Not started / In progress / Found / Skipped
    notes: Optional[str] = ""
    created_at: str = Field(default_factory=utc_now_iso)


class MissingItemCreate(BaseModel):
    item_needed: str
    category: str
    tax_year: str
    priority: str
    where_to_find: Optional[str] = ""
    why_matters: Optional[str] = ""
    status: Optional[str] = "Not started"
    notes: Optional[str] = ""


class MissingItemUpdate(BaseModel):
    item_needed: Optional[str] = None
    category: Optional[str] = None
    tax_year: Optional[str] = None
    priority: Optional[str] = None
    where_to_find: Optional[str] = None
    why_matters: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


# =================== Drive helpers ===================

async def get_drive_credentials_doc():
    return await db.drive_credentials.find_one({"key": SINGLETON_KEY}, {"_id": 0})


async def save_drive_credentials(credentials: Credentials):
    doc = {
        "key": SINGLETON_KEY,
        "access_token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
        "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
        "updated_at": utc_now_iso(),
    }
    await db.drive_credentials.update_one({"key": SINGLETON_KEY}, {"$set": doc}, upsert=True)


async def get_drive_service():
    creds_doc = await get_drive_credentials_doc()
    if not creds_doc:
        raise HTTPException(status_code=400, detail="Google Drive not connected.")
    creds = Credentials(
        token=creds_doc["access_token"],
        refresh_token=creds_doc.get("refresh_token"),
        token_uri=creds_doc["token_uri"],
        client_id=creds_doc["client_id"],
        client_secret=creds_doc["client_secret"],
        scopes=creds_doc["scopes"],
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleRequest())
        await db.drive_credentials.update_one(
            {"key": SINGLETON_KEY},
            {"$set": {
                "access_token": creds.token,
                "expiry": creds.expiry.isoformat() if creds.expiry else None,
                "updated_at": utc_now_iso(),
            }},
        )
    return build('drive', 'v3', credentials=creds)


async def get_or_create_folders():
    """Ensure parent folder + all subfolders exist. Returns config doc."""
    cfg = await db.drive_config.find_one({"key": SINGLETON_KEY}, {"_id": 0})
    if cfg and cfg.get("parent_folder_id"):
        return cfg
    service = await get_drive_service()
    # Find or create parent
    parent_name = "Tax Evidence Vault"
    q = f"mimeType='application/vnd.google-apps.folder' and name='{parent_name}' and trashed=false"
    res = service.files().list(q=q, fields="files(id, name)").execute()
    files = res.get('files', [])
    if files:
        parent_id = files[0]['id']
    else:
        folder_meta = {'name': parent_name, 'mimeType': 'application/vnd.google-apps.folder'}
        parent = service.files().create(body=folder_meta, fields='id').execute()
        parent_id = parent['id']
    # Create subfolders
    sub_ids = {}
    for folder_name, _ in FOLDER_STRUCTURE:
        q = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and '{parent_id}' in parents and trashed=false"
        res = service.files().list(q=q, fields="files(id, name)").execute()
        files = res.get('files', [])
        if files:
            sub_ids[folder_name] = files[0]['id']
        else:
            meta = {'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [parent_id]}
            f = service.files().create(body=meta, fields='id').execute()
            sub_ids[folder_name] = f['id']
    cfg = {
        "key": SINGLETON_KEY,
        "parent_folder_id": parent_id,
        "parent_folder_name": parent_name,
        "subfolders": sub_ids,
        "updated_at": utc_now_iso(),
    }
    await db.drive_config.update_one({"key": SINGLETON_KEY}, {"$set": cfg}, upsert=True)
    return cfg


# =================== Drive OAuth routes ===================

@api_router.get("/drive/status")
async def drive_status():
    creds = await get_drive_credentials_doc()
    cfg = await db.drive_config.find_one({"key": SINGLETON_KEY}, {"_id": 0})
    return {
        "connected": bool(creds),
        "initialized": bool(cfg and cfg.get("parent_folder_id")),
        "parent_folder_id": (cfg or {}).get("parent_folder_id"),
        "parent_folder_name": (cfg or {}).get("parent_folder_name"),
        "subfolders": (cfg or {}).get("subfolders", {}),
    }


@api_router.get("/drive/connect")
async def drive_connect():
    redirect_uri = os.environ["GOOGLE_DRIVE_REDIRECT_URI"]
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": os.environ["GOOGLE_CLIENT_ID"],
                "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        },
        scopes=DRIVE_SCOPES,
        redirect_uri=redirect_uri,
    )
    authorization_url, _state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent',
    )
    return {"authorization_url": authorization_url}


@api_router.get("/drive/callback")
async def drive_callback(code: str = Query(...)):
    try:
        redirect_uri = os.environ["GOOGLE_DRIVE_REDIRECT_URI"]
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": os.environ["GOOGLE_CLIENT_ID"],
                    "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri],
                }
            },
            scopes=None,
            redirect_uri=redirect_uri,
        )
        flow.fetch_token(code=code)
        credentials = flow.credentials
        required = {"https://www.googleapis.com/auth/drive"}
        granted = set(credentials.scopes or [])
        if not required.issubset(granted):
            missing = required - granted
            raise HTTPException(status_code=400, detail=f"Missing Drive scopes: {missing}")
        await save_drive_credentials(credentials)
        # Auto-initialize folder structure so user doesn't need a second click
        try:
            await get_or_create_folders()
        except Exception as e:
            logger.warning(f"Auto-folder-init after OAuth failed (will retry on demand): {e}")
        frontend = os.environ["FRONTEND_URL"]
        return RedirectResponse(url=f"{frontend}/settings?drive=connected")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Drive callback failed")
        frontend = os.environ["FRONTEND_URL"]
        return RedirectResponse(url=f"{frontend}/settings?drive=error&msg={str(e)[:200]}")


@api_router.post("/drive/initialize")
async def drive_initialize():
    cfg = await get_or_create_folders()
    return cfg


@api_router.post("/drive/disconnect")
async def drive_disconnect():
    await db.drive_credentials.delete_many({"key": SINGLETON_KEY})
    await db.drive_config.delete_many({"key": SINGLETON_KEY})
    return {"ok": True}


# =================== Seed / preload ===================

@api_router.post("/seed/missing-evidence")
async def seed_missing():
    existing = await db.missing_items.count_documents({})
    if existing > 0:
        return {"ok": True, "skipped": True, "existing": existing}
    docs = []
    for item in MISSING_PRELOAD:
        m = MissingItem(**item)
        docs.append(m.model_dump())
    await db.missing_items.insert_many(docs)
    return {"ok": True, "inserted": len(docs)}


@api_router.post("/seed/payg-income")
async def seed_payg():
    existing = await db.figures.count_documents({"figure_type": "payg_income"})
    if existing > 0:
        return {"ok": True, "skipped": True, "existing": existing}
    docs = []
    for item in PAYG_PRELOAD:
        f = Figure(
            figure_type="payg_income",
            amount=item["amount"],
            description=item["employer"],
            source_document=f"Preloaded PAYG ({item['employer']})",
            tax_year=item["tax_year"],
            category="PAYG Income",
        )
        docs.append(f.model_dump())
    await db.figures.insert_many(docs)
    return {"ok": True, "inserted": len(docs)}


@api_router.post("/seed/all")
async def seed_all():
    r1 = await seed_missing()
    r2 = await seed_payg()
    return {"missing": r1, "payg": r2}


# =================== Documents ===================

@api_router.post("/documents")
async def upload_document(
    file: UploadFile = File(...),
    name: str = Form(...),
    tax_year: str = Form(...),
    category: str = Form(...),
    notes: str = Form(""),
    accountant_review: str = Form("No"),
):
    if category not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category: {category}")
    if tax_year not in TAX_YEARS:
        raise HTTPException(status_code=400, detail=f"Invalid tax_year: {tax_year}")

    content = await file.read()
    file_type = file.content_type or "application/octet-stream"
    folder_name = CATEGORY_TO_FOLDER.get(category, "10 Missing Evidence")

    drive_file_id = None
    drive_link = None
    drive_folder_id = None

    # Drive is the only storage backend (per user choice). Require connection.
    creds = await get_drive_credentials_doc()
    if not creds:
        raise HTTPException(
            status_code=400,
            detail="Google Drive not connected. Open Settings → Connect Google Drive before uploading.",
        )
    try:
        cfg = await get_or_create_folders()
        drive_folder_id = cfg["subfolders"].get(folder_name)
        service = await get_drive_service()
        media = MediaIoBaseUpload(io.BytesIO(content), mimetype=file_type, resumable=False)
        meta = {'name': file.filename, 'parents': [drive_folder_id]}
        res = service.files().create(
            body=meta,
            media_body=media,
            fields='id, webViewLink, webContentLink',
        ).execute()
        drive_file_id = res.get('id')
        drive_link = res.get('webViewLink')
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Drive upload failed")
        raise HTTPException(status_code=500, detail=f"Drive upload failed: {e}")

    doc = Document(
        name=name,
        file_type=file_type,
        original_filename=file.filename,
        tax_year=tax_year,
        category=category,
        notes=notes,
        accountant_review=accountant_review,
        status="Accountant review" if accountant_review == "Yes" else "Uploaded only",
        drive_file_id=drive_file_id,
        drive_link=drive_link,
        drive_folder_id=drive_folder_id,
        drive_folder_name=folder_name,
        size_bytes=len(content),
    )
    await db.documents.insert_one(doc.model_dump())
    return doc


@api_router.get("/documents")
async def list_documents(
    category: Optional[str] = None,
    tax_year: Optional[str] = None,
    status: Optional[str] = None,
    accountant_review: Optional[str] = None,
):
    q = {}
    if category:
        q["category"] = category
    if tax_year:
        if tax_year in ("FY2024", "FY2025"):
            q["tax_year"] = {"$in": [tax_year, "Both"]}
        else:
            q["tax_year"] = tax_year
    if status:
        q["status"] = status
    if accountant_review:
        q["accountant_review"] = accountant_review
    cursor = db.documents.find(q, {"_id": 0}).sort("created_at", -1)
    return await cursor.to_list(2000)


@api_router.get("/documents/{doc_id}")
async def get_document(doc_id: str):
    doc = await db.documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


@api_router.patch("/documents/{doc_id}")
async def update_document(doc_id: str, payload: DocumentUpdate):
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    update["updated_at"] = utc_now_iso()
    res = await db.documents.update_one({"id": doc_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(404, "Document not found")
    return await db.documents.find_one({"id": doc_id}, {"_id": 0})


@api_router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    doc = await db.documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Document not found")
    # Try delete from drive
    if doc.get("drive_file_id"):
        try:
            service = await get_drive_service()
            service.files().delete(fileId=doc["drive_file_id"]).execute()
        except Exception as e:
            logger.warning(f"Drive delete failed (continuing): {e}")
    await db.documents.delete_one({"id": doc_id})
    await db.figures.delete_many({"document_id": doc_id})
    return {"ok": True}


# =================== Figures ===================

@api_router.post("/figures")
async def create_figure(payload: FigureCreate):
    fig = Figure(**payload.model_dump())
    await db.figures.insert_one(fig.model_dump())
    return fig


@api_router.get("/figures")
async def list_figures(document_id: Optional[str] = None, tax_year: Optional[str] = None):
    q = {}
    if document_id:
        q["document_id"] = document_id
    if tax_year:
        q["tax_year"] = tax_year
    cursor = db.figures.find(q, {"_id": 0}).sort("created_at", -1)
    return await cursor.to_list(2000)


@api_router.delete("/figures/{fig_id}")
async def delete_figure(fig_id: str):
    res = await db.figures.delete_one({"id": fig_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Figure not found")
    return {"ok": True}


# =================== Missing items ===================

@api_router.get("/missing-evidence")
async def list_missing(priority: Optional[str] = None, status: Optional[str] = None):
    q = {}
    if priority:
        q["priority"] = priority
    if status:
        q["status"] = status
    cursor = db.missing_items.find(q, {"_id": 0}).sort("created_at", 1)
    return await cursor.to_list(2000)


@api_router.post("/missing-evidence")
async def create_missing(payload: MissingItemCreate):
    item = MissingItem(**payload.model_dump())
    await db.missing_items.insert_one(item.model_dump())
    return item


@api_router.patch("/missing-evidence/{item_id}")
async def update_missing(item_id: str, payload: MissingItemUpdate):
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    res = await db.missing_items.update_one({"id": item_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(404, "Item not found")
    return await db.missing_items.find_one({"id": item_id}, {"_id": 0})


@api_router.delete("/missing-evidence/{item_id}")
async def delete_missing(item_id: str):
    res = await db.missing_items.delete_one({"id": item_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Item not found")
    return {"ok": True}


# =================== Dashboard ===================

def card_status(card, total, review_count):
    if card["type"] == "review":
        if review_count == 0:
            return "Not started"
        return "Accountant review"
    if card["type"] == "missing":
        return "Partial" if total > 0 else "Not started"
    if total == 0:
        return "Not started"
    if review_count > 0:
        return "Accountant review"
    return "Partial"


@api_router.get("/dashboard")
async def dashboard():
    all_docs = await db.documents.find({}, {"_id": 0}).to_list(5000)
    cards = []
    for card in DASHBOARD_CARDS:
        if card["type"] == "tax_year":
            matching = [d for d in all_docs if d["tax_year"] == card["value"] or d["tax_year"] == "Both"]
        elif card["type"] == "category":
            matching = [d for d in all_docs if d["category"] == card["value"]]
        elif card["type"] == "review":
            matching = [d for d in all_docs if d.get("accountant_review") == "Yes"]
        elif card["type"] == "missing":
            count = await db.missing_items.count_documents({"status": {"$ne": "Found"}})
            cards.append({**card, "documents": count, "status": "Partial" if count > 0 else "Complete"})
            continue
        else:
            matching = []
        total = len(matching)
        review = sum(1 for d in matching if d.get("accountant_review") == "Yes")
        cards.append({**card, "documents": total, "status": card_status(card, total, review)})
    return {"cards": cards, "total_documents": len(all_docs)}


# =================== Reference data ===================

@api_router.get("/reference")
async def reference():
    return {
        "categories": CATEGORIES,
        "tax_years": TAX_YEARS,
        "status_options": STATUS_OPTIONS,
        "priorities": PRIORITIES,
        "folder_structure": [f for f, _ in FOLDER_STRUCTURE],
        "category_to_folder": CATEGORY_TO_FOLDER,
    }


# =================== Reports ===================

def csv_response(headers: list, rows: list, filename: str) -> Response:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for r in rows:
        writer.writerow(r)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api_router.get("/reports/evidence-register.csv")
async def export_evidence_register():
    docs = await db.documents.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    figs_by_doc = {}
    async for f in db.figures.find({"document_id": {"$ne": None}}, {"_id": 0}):
        figs_by_doc.setdefault(f["document_id"], []).append(f)
    headers = [
        "Date uploaded", "Document name", "File type", "Google Drive folder",
        "Google Drive link", "Tax year", "Category", "Key figures found",
        "What it proves", "Missing follow-up", "Accountant review required",
        "Status", "Notes",
    ]
    rows = []
    for d in docs:
        figs = figs_by_doc.get(d["id"], [])
        kf = d.get("key_figures_found") or "; ".join(
            f"{x['figure_type']}={x['amount']}" for x in figs
        )
        rows.append([
            d.get("created_at", ""),
            d.get("name", ""),
            d.get("file_type", ""),
            d.get("drive_folder_name", ""),
            d.get("drive_link", ""),
            d.get("tax_year", ""),
            d.get("category", ""),
            kf,
            d.get("what_it_proves", ""),
            d.get("missing_followup", ""),
            d.get("accountant_review", ""),
            d.get("status", ""),
            d.get("notes", ""),
        ])
    return csv_response(headers, rows, "evidence-register.csv")


@api_router.get("/reports/missing-evidence.csv")
async def export_missing():
    items = await db.missing_items.find({}, {"_id": 0}).to_list(5000)
    headers = ["Item needed", "Category", "Tax year", "Priority", "Where to find it", "Why it matters", "Status", "Notes"]
    rows = [[i.get("item_needed", ""), i.get("category", ""), i.get("tax_year", ""), i.get("priority", ""),
             i.get("where_to_find", ""), i.get("why_matters", ""), i.get("status", ""), i.get("notes", "")] for i in items]
    return csv_response(headers, rows, "missing-evidence.csv")


@api_router.get("/reports/documents-by-category.csv")
async def export_by_category():
    docs = await db.documents.find({}, {"_id": 0}).to_list(5000)
    headers = ["Category", "Tax year", "Document count"]
    counts = {}
    for d in docs:
        key = (d.get("category", ""), d.get("tax_year", ""))
        counts[key] = counts.get(key, 0) + 1
    rows = [[k[0], k[1], v] for k, v in sorted(counts.items())]
    return csv_response(headers, rows, "documents-by-category.csv")


@api_router.get("/reports/accountant-summary.pdf")
async def export_accountant_pdf():
    docs = await db.documents.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    figs = await db.figures.find({}, {"_id": 0}).to_list(5000)
    missing = await db.missing_items.find({}, {"_id": 0}).to_list(5000)
    review_docs = [d for d in docs if d.get("accountant_review") == "Yes" or d.get("status") == "Accountant review"]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18*mm, rightMargin=18*mm, topMargin=18*mm, bottomMargin=18*mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('T', parent=styles['Title'], fontName='Helvetica-Bold', fontSize=18, spaceAfter=6)
    h2 = ParagraphStyle('H2', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=12, spaceBefore=14, spaceAfter=6)
    body = ParagraphStyle('B', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leading=12)
    small = ParagraphStyle('S', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10, textColor=colors.grey)

    story = []
    story.append(Paragraph("Tax Evidence Vault — Accountant Summary", title_style))
    story.append(Paragraph(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", small))
    story.append(Paragraph("Single-user evidence pack for FY2024 & FY2025 (overdue). Figures are manually entered and may require accountant verification.", body))

    # Documents received
    story.append(Paragraph(f"Documents received ({len(docs)})", h2))
    if docs:
        rows = [["Date", "Name", "Tax Year", "Category", "Status", "Review"]]
        for d in docs[:200]:
            rows.append([
                (d.get("created_at") or "")[:10],
                (d.get("name") or "")[:40],
                d.get("tax_year", ""),
                d.get("category", ""),
                d.get("status", ""),
                d.get("accountant_review", ""),
            ])
        t = Table(rows, repeatRows=1, colWidths=[22*mm, 55*mm, 18*mm, 32*mm, 30*mm, 18*mm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("No documents uploaded yet.", body))

    # Key figures
    story.append(Paragraph(f"Key figures entered ({len(figs)})", h2))
    if figs:
        rows = [["Tax Year", "Type", "Amount (AUD)", "Description", "Source"]]
        figs_sorted = sorted(figs, key=lambda x: (x.get("tax_year", ""), x.get("figure_type", "")))
        totals = {}
        for f in figs_sorted:
            rows.append([
                f.get("tax_year", ""),
                f.get("figure_type", ""),
                f"{float(f.get('amount', 0)):,.2f}",
                (f.get("description") or "")[:50],
                (f.get("source_document") or "")[:30],
            ])
            key = (f.get("tax_year", ""), f.get("figure_type", ""))
            totals[key] = totals.get(key, 0) + float(f.get("amount", 0))
        t = Table(rows, repeatRows=1, colWidths=[20*mm, 28*mm, 28*mm, 60*mm, 38*mm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('ALIGN', (2, 1), (2, -1), 'RIGHT'),
        ]))
        story.append(t)
        story.append(Spacer(1, 8))
        story.append(Paragraph("Subtotals by tax year & type", h2))
        rows2 = [["Tax Year", "Type", "Total (AUD)"]]
        for (ty, ft), v in sorted(totals.items()):
            rows2.append([ty, ft, f"{v:,.2f}"])
        t2 = Table(rows2, repeatRows=1, colWidths=[30*mm, 40*mm, 40*mm])
        t2.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('ALIGN', (2, 1), (2, -1), 'RIGHT'),
        ]))
        story.append(t2)
    else:
        story.append(Paragraph("No figures entered.", body))

    # Missing
    story.append(PageBreak())
    open_missing = [m for m in missing if m.get("status") != "Found"]
    story.append(Paragraph(f"Outstanding evidence ({len(open_missing)})", h2))
    if open_missing:
        rows = [["Priority", "Item", "Category", "FY", "Where to find"]]
        for m in sorted(open_missing, key=lambda x: PRIORITIES.index(x.get("priority", "Later")) if x.get("priority") in PRIORITIES else 99):
            rows.append([
                m.get("priority", ""),
                (m.get("item_needed") or "")[:55],
                m.get("category", ""),
                m.get("tax_year", ""),
                (m.get("where_to_find") or "")[:55],
            ])
        t = Table(rows, repeatRows=1, colWidths=[22*mm, 60*mm, 30*mm, 18*mm, 45*mm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(t)

    # Accountant review items
    story.append(Paragraph(f"Accountant review items ({len(review_docs)})", h2))
    if review_docs:
        rows = [["Name", "Tax Year", "Category", "Notes"]]
        for d in review_docs:
            rows.append([
                (d.get("name") or "")[:40],
                d.get("tax_year", ""),
                d.get("category", ""),
                (d.get("notes") or "")[:60],
            ])
        t = Table(rows, repeatRows=1, colWidths=[55*mm, 20*mm, 32*mm, 65*mm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("No items flagged for accountant review.", body))

    doc.build(story)
    pdf_bytes = buf.getvalue()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="accountant-summary.pdf"'},
    )


@api_router.get("/")
async def root():
    return {"app": "Tax Evidence Vault", "stage": 1}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    # Auto-seed on first run
    if await db.missing_items.count_documents({}) == 0:
        await db.missing_items.insert_many([MissingItem(**i).model_dump() for i in MISSING_PRELOAD])
    if await db.figures.count_documents({"figure_type": "payg_income"}) == 0:
        await db.figures.insert_many([
            Figure(
                figure_type="payg_income",
                amount=i["amount"],
                description=i["employer"],
                source_document=f"Preloaded PAYG ({i['employer']})",
                tax_year=i["tax_year"],
                category="PAYG Income",
            ).model_dump()
            for i in PAYG_PRELOAD
        ])


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
