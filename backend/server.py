from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import RedirectResponse, StreamingResponse, Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import io
import logging
import csv
import json
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

DRIVE_SCOPES = ['https://www.googleapis.com/auth/drive.file']

# Local fallback storage when Drive is not connected
LOCAL_UPLOADS_DIR = ROOT_DIR / "uploads"
LOCAL_UPLOADS_DIR.mkdir(exist_ok=True)

FOLDER_STRUCTURE = [
    ("00 Inbox", "Inbox"),
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
    storage: str = "drive"  # "drive" or "local"
    local_path: Optional[str] = None
    manual_drive_folder: Optional[str] = ""
    manual_drive_link: Optional[str] = ""
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
    manual_drive_folder: Optional[str] = None
    manual_drive_link: Optional[str] = None


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
    """Ensure parent folder + all subfolders exist. Returns config doc.
    Idempotent: re-checks for any new/missing subfolders in FOLDER_STRUCTURE."""
    cfg = await db.drive_config.find_one({"key": SINGLETON_KEY}, {"_id": 0})
    parent_id = (cfg or {}).get("parent_folder_id")
    sub_ids: dict = dict((cfg or {}).get("subfolders") or {})
    expected = [name for name, _ in FOLDER_STRUCTURE]
    if cfg and parent_id and all(n in sub_ids for n in expected):
        return cfg
    service = await get_drive_service()
    parent_name = "Tax Evidence Vault"
    if not parent_id:
        q = f"mimeType='application/vnd.google-apps.folder' and name='{parent_name}' and trashed=false"
        res = service.files().list(q=q, fields="files(id, name)").execute()
        files = res.get('files', [])
        if files:
            parent_id = files[0]['id']
        else:
            folder_meta = {'name': parent_name, 'mimeType': 'application/vnd.google-apps.folder'}
            parent = service.files().create(body=folder_meta, fields='id').execute()
            parent_id = parent['id']
    for folder_name, _ in FOLDER_STRUCTURE:
        if folder_name in sub_ids:
            continue
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
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent',
    )
    # google-auth-oauthlib auto-generates a PKCE code_verifier on
    # authorization_url(). It must be persisted and replayed on the token
    # exchange in /api/drive/callback or Google returns
    # `invalid_grant: Missing code verifier`. We are a confidential
    # server-side client; persisting in the DB (keyed by the oauth `state`)
    # is the correct pattern.
    await db.drive_attempts.update_one(
        {"key": SINGLETON_KEY},
        {"$set": {
            "key": SINGLETON_KEY,
            "started_at": utc_now_iso(),
            "authorization_url": authorization_url,
            "redirect_uri": redirect_uri,
            "scopes_requested": DRIVE_SCOPES,
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "oauth_state": state,
            "code_verifier": getattr(flow, "code_verifier", None),
            "callback_received": False,
        }},
        upsert=True,
    )
    logger.info(
        f"Drive OAuth attempt started, state={state[:6]}..., "
        f"pkce={'yes' if getattr(flow, 'code_verifier', None) else 'no'}"
    )
    return {"authorization_url": authorization_url}


@api_router.get("/drive/callback")
async def drive_callback(
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
    error_description: str = Query(None),
):
    frontend = os.environ["FRONTEND_URL"]
    # Google sometimes redirects back with ?error=access_denied&error_description=...
    if error:
        await db.drive_errors.update_one(
            {"key": SINGLETON_KEY},
            {"$set": {
                "key": SINGLETON_KEY,
                "error": error,
                "error_description": error_description or "",
                "source": "google_redirect",
                "timestamp": utc_now_iso(),
            }},
            upsert=True,
        )
        await db.drive_attempts.update_one(
            {"key": SINGLETON_KEY},
            {"$set": {"callback_received": True, "callback_result": "error", "callback_at": utc_now_iso()}},
        )
        logger.error(f"Drive OAuth error from Google: {error} — {error_description}")
        return RedirectResponse(
            url=f"{frontend}/settings?drive=error&code={error}&msg={(error_description or '')[:300]}"
        )
    if not code:
        await db.drive_errors.update_one(
            {"key": SINGLETON_KEY},
            {"$set": {
                "key": SINGLETON_KEY,
                "error": "missing_code",
                "error_description": "Google redirected back without an authorization code.",
                "source": "callback",
                "timestamp": utc_now_iso(),
            }},
            upsert=True,
        )
        return RedirectResponse(url=f"{frontend}/settings?drive=error&code=missing_code")
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
            scopes=DRIVE_SCOPES,
            redirect_uri=redirect_uri,
        )
        # Replay the PKCE code_verifier we generated in /api/drive/connect.
        # Without this, Google rejects token exchange with
        # `invalid_grant: Missing code verifier`.
        attempt = await db.drive_attempts.find_one({"key": SINGLETON_KEY}, {"_id": 0})
        if attempt and attempt.get("code_verifier"):
            # Match by state when provided to defend against stale attempts.
            if state and attempt.get("oauth_state") and attempt["oauth_state"] != state:
                logger.warning(
                    f"OAuth state mismatch — stored={attempt['oauth_state'][:6]}..., "
                    f"received={state[:6]}... — using stored verifier anyway (single-user app)"
                )
            flow.code_verifier = attempt["code_verifier"]
            logger.info("Restored PKCE code_verifier from drive_attempts")
        flow.fetch_token(code=code)
        credentials = flow.credentials
        raw_granted = credentials.scopes or []
        if isinstance(raw_granted, str):
            raw_granted = raw_granted.split()
        granted = set(raw_granted)
        logger.info(f"OAuth granted scopes (raw): {raw_granted}")
        has_drive_file = any('drive.file' in s for s in granted)
        if not has_drive_file:
            err_msg = f"drive.file scope not granted. Got: {list(granted)}"
            await db.drive_errors.update_one(
                {"key": SINGLETON_KEY},
                {"$set": {
                    "key": SINGLETON_KEY,
                    "error": "missing_scopes",
                    "error_description": err_msg,
                    "source": "callback",
                    "timestamp": utc_now_iso(),
                }},
                upsert=True,
            )
            return RedirectResponse(url=f"{frontend}/settings?drive=error&code=missing_scopes&msg={err_msg}")
        await save_drive_credentials(credentials)
        # Clear any prior error since we are now connected
        await db.drive_errors.delete_many({"key": SINGLETON_KEY})
        await db.drive_attempts.update_one(
            {"key": SINGLETON_KEY},
            {"$set": {"callback_received": True, "callback_result": "success", "callback_at": utc_now_iso()}},
        )
        try:
            await get_or_create_folders()
        except Exception as e:
            logger.warning(f"Auto-folder-init after OAuth failed (will retry on demand): {e}")
        return RedirectResponse(url=f"{frontend}/settings?drive=connected")
    except Exception as e:
        # Try to extract Google's structured error body
        err_msg = str(e)
        err_body = getattr(e, "response", None)
        try:
            if err_body is not None:
                err_msg = f"{e} :: body={err_body.text[:500]}"
        except Exception:
            pass
        await db.drive_errors.update_one(
            {"key": SINGLETON_KEY},
            {"$set": {
                "key": SINGLETON_KEY,
                "error": "fetch_token_failed",
                "error_description": err_msg[:1000],
                "source": "callback",
                "timestamp": utc_now_iso(),
            }},
            upsert=True,
        )
        logger.exception("Drive callback failed")
        return RedirectResponse(url=f"{frontend}/settings?drive=error&code=fetch_token_failed&msg={err_msg[:300]}")


@api_router.post("/drive/initialize")
async def drive_initialize():
    cfg = await get_or_create_folders()
    return cfg


@api_router.post("/drive/disconnect")
async def drive_disconnect():
    await db.drive_credentials.delete_many({"key": SINGLETON_KEY})
    await db.drive_config.delete_many({"key": SINGLETON_KEY})
    await db.drive_errors.delete_many({"key": SINGLETON_KEY})
    return {"ok": True}


@api_router.get("/diagnostics")
async def diagnostics():
    creds = await get_drive_credentials_doc()
    cfg = await db.drive_config.find_one({"key": SINGLETON_KEY}, {"_id": 0})
    last_err = await db.drive_errors.find_one({"key": SINGLETON_KEY}, {"_id": 0})
    last_attempt = await db.drive_attempts.find_one({"key": SINGLETON_KEY}, {"_id": 0})
    # If we started an attempt but Google never bounced back, surface a
    # synthesised "silent failure" so the panel isn't useless.
    silent_block = None
    if last_attempt and not last_attempt.get("callback_received") and not creds:
        silent_block = {
            "error": "google_blocked_before_callback",
            "error_description": (
                "Backend generated an OAuth URL but Google never redirected back to /api/drive/callback. "
                "This means Google's consent page itself rejected the request (the 403 page you saw) and the "
                "user/browser remained on accounts.google.com. No backend exception exists because nothing was "
                "delivered to us. See the troubleshooting list on this page — the cause is in your Google Cloud "
                "Console (consent screen scopes, app status, or client configuration), not in this app."
            ),
            "source": "diagnostics",
            "timestamp": last_attempt.get("started_at"),
        }
    return {
        "oauth_client_id": os.environ.get("GOOGLE_CLIENT_ID"),
        "redirect_uri": os.environ.get("GOOGLE_DRIVE_REDIRECT_URI"),
        "frontend_url": os.environ.get("FRONTEND_URL"),
        "requested_scopes": DRIVE_SCOPES,
        "drive_connected": bool(creds),
        "drive_initialized": bool(cfg and cfg.get("parent_folder_id")),
        "granted_scopes": (creds or {}).get("scopes") if creds else None,
        "credentials_updated_at": (creds or {}).get("updated_at") if creds else None,
        "last_error": last_err or silent_block,
        "last_attempt": last_attempt,
    }


@api_router.delete("/diagnostics/last-error")
async def clear_last_error():
    await db.drive_errors.delete_many({"key": SINGLETON_KEY})
    await db.drive_attempts.delete_many({"key": SINGLETON_KEY})
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
    manual_drive_folder: str = Form(""),
    manual_drive_link: str = Form(""),
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
    storage = "local"
    local_path: Optional[str] = None

    creds = await get_drive_credentials_doc()
    if creds:
        # Try Drive upload. On failure, fall back to local storage with a flag.
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
            storage = "drive"
        except Exception as e:
            logger.exception("Drive upload failed — falling back to local storage")
            await db.drive_errors.update_one(
                {"key": SINGLETON_KEY},
                {"$set": {
                    "key": SINGLETON_KEY,
                    "error": "drive_upload_failed",
                    "error_description": str(e)[:1000],
                    "source": "upload",
                    "timestamp": utc_now_iso(),
                }},
                upsert=True,
            )
            storage = "local"

    if storage == "local":
        doc_id = str(uuid.uuid4())
        safe_name = file.filename.replace("/", "_")
        local_file = LOCAL_UPLOADS_DIR / f"{doc_id}__{safe_name}"
        with open(local_file, "wb") as fh:
            fh.write(content)
        local_path = str(local_file)
        doc = Document(
            id=doc_id,
            name=name,
            file_type=file_type,
            original_filename=file.filename,
            tax_year=tax_year,
            category=category,
            notes=notes,
            accountant_review=accountant_review,
            status="Accountant review" if accountant_review == "Yes" else "Uploaded only",
            drive_folder_name=folder_name,
            storage="local",
            local_path=local_path,
            manual_drive_folder=manual_drive_folder,
            manual_drive_link=manual_drive_link,
            size_bytes=len(content),
        )
    else:
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
            storage="drive",
            manual_drive_folder=manual_drive_folder,
            manual_drive_link=manual_drive_link,
            size_bytes=len(content),
        )
    await db.documents.insert_one(doc.model_dump())
    return doc


@api_router.get("/documents/{doc_id}/download")
async def download_document(doc_id: str):
    doc = await db.documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.get("storage") != "local" or not doc.get("local_path"):
        raise HTTPException(400, "Document is stored in Google Drive — use the Drive link instead.")
    path = doc["local_path"]
    if not os.path.exists(path):
        raise HTTPException(404, "Local file missing on disk.")

    def _iter():
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(64 * 1024)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        _iter(),
        media_type=doc.get("file_type") or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{doc.get("original_filename", "file")}"'},
    )


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
    # Stage 5 — any user PATCH on a document is treated as a manual confirmation
    # so later AI runs don't overwrite their work.
    update["user_confirmed"] = True
    # Stage 5 — if the user clears the accountant_review flag and the doc
    # isn't red-risk, auto-set the document to Complete and drop the
    # required flag in lockstep.
    existing = await db.documents.find_one({"id": doc_id}, {"_id": 0})
    if existing is None:
        raise HTTPException(404, "Document not found")
    if update.get("accountant_review") == "No" and existing.get("risk_level") != "Red":
        update["accountant_review_required"] = False
        update["status"] = "Complete"
    res = await db.documents.update_one({"id": doc_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(404, "Document not found")
    return await db.documents.find_one({"id": doc_id}, {"_id": 0})


@api_router.patch("/documents/{doc_id}/figures")
async def update_document_figures(doc_id: str, payload: dict):
    figures = payload.get("figures") or []
    await db.documents.update_one(
        {"id": doc_id},
        {"$set": {
            "headline_figures_json": figures,
            "user_confirmed": True,  # Stage 5 — manual figure edit is a confirmation
            "updated_at": utc_now_iso(),
        }},
    )
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
    # Remove local file if present
    if doc.get("local_path"):
        try:
            if os.path.exists(doc["local_path"]):
                os.remove(doc["local_path"])
        except Exception as e:
            logger.warning(f"Local file delete failed: {e}")
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
    cursor = db.missing_items.find(q, {"_id": 0}).sort([("priority", 1), ("created_at", 1)])
    return await cursor.to_list(2000)


@api_router.get("/missing-evidence/next")
async def next_missing():
    item = await me.get_next_best_document(db)
    return {"item": item}


@api_router.post("/missing-evidence/seed")
async def seed_missing_v2():
    return await me.seed_missing_evidence(db)


@api_router.post("/missing-evidence")
async def create_missing(payload: MissingItemCreate):
    item = MissingItem(**payload.model_dump())
    d = item.model_dump()
    d["item_description"] = d.get("item_needed", "")
    d["status"] = d.get("status") or "Outstanding"
    d["matched_document_id"] = None
    d["matched_document_name"] = None
    d["match_confidence"] = None
    d["match_reason"] = None
    d["updated_at"] = me.utc_now_iso()
    await db.missing_items.insert_one(d)
    # `insert_one` mutates `d` by adding ObjectId `_id` which can't be
    # JSON-serialised — strip it before returning.
    d.pop("_id", None)
    return d


@api_router.patch("/missing-evidence/{item_id}")
async def update_missing(item_id: str, payload: dict):
    allowed = {"status", "notes", "notes_user", "matched_document_id", "matched_document_name",
               "match_confidence", "match_reason", "priority", "tax_year",
               "category", "item_description"}
    patch = {k: v for k, v in payload.items() if k in allowed and v is not None}
    if "status" in patch and patch["status"] not in me.ALLOWED_STATUS:
        raise HTTPException(400, f"status must be one of {me.ALLOWED_STATUS}")
    if "match_confidence" in patch and patch["match_confidence"] not in me.ALLOWED_MATCH_CONFIDENCE:
        raise HTTPException(400, f"match_confidence must be one of {me.ALLOWED_MATCH_CONFIDENCE}")
    patch["updated_at"] = me.utc_now_iso()
    if "item_description" in patch:
        patch["item_needed"] = patch["item_description"]
    # Stage 4.5: track manual overrides so auto-matching doesn't trample them.
    # Reset to "Outstanding" clears the manual flag (explicit re-evaluation
    # signal from the user).
    if "status" in patch:
        if patch["status"] == "Outstanding":
            patch["status_source"] = "system"
        else:
            patch["status_source"] = "user"
            patch["status_updated_by"] = "user"
        patch["status_updated_at"] = me.utc_now_iso()
    res = await db.missing_items.update_one({"id": item_id}, {"$set": patch})
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
            # Stage 4.5: count only items the user still owes — i.e. not yet
            # confirmed Received and not flagged Not applicable.
            OPEN_STATUSES = ["Outstanding", "Possible Match", "Accountant Review"]
            count = await db.missing_items.count_documents({"status": {"$in": OPEN_STATUSES}})
            cards.append({**card, "documents": count, "status": "Partial" if count > 0 else "Complete"})
            continue
        else:
            matching = []
        total = len(matching)
        review = sum(1 for d in matching if d.get("accountant_review") == "Yes")
        cards.append({**card, "documents": total, "status": card_status(card, total, review)})
    return {"cards": cards, "total_documents": len(all_docs)}


@api_router.get("/dashboard/stats")
async def dashboard_stats():
    """Stage 5 — compact stat band for the dashboard top row.

    Returns total + per-category doc counts, plus the "classified",
    "needs_review", and "missing_critical" aggregates the UI surfaces as
    headline numbers. Single-user app, no auth.
    """
    # Total documents
    total = await db.documents.count_documents({})

    # Per-category counts — uses the canonical folder names.
    categories: dict[str, int] = {}
    for cat in [
        "00 Inbox", "01 ATO", "02 PAYG Income", "03 Airbnb",
        "04 Waggrakine Rental", "05 Heathridge", "06 Revive",
        "07 Bank Statements", "08 Salary Packaging Maxxia",
        "09 Accountant Review", "10 Missing Evidence", "11 Final Accountant Pack",
    ]:
        categories[cat] = await db.documents.count_documents({"category": cat})

    # Documents that were confidently filed (not Inbox, conf Confirmed/Likely).
    classified = await db.documents.count_documents({
        "category": {"$ne": "00 Inbox"},
        "category_confidence": {"$in": ["Confirmed", "Likely"]},
    })

    # Anything the human needs to look at.
    needs_review = await db.documents.count_documents({
        "$or": [
            {"category": "00 Inbox"},
            {"category": "09 Accountant Review"},
            {"accountant_review_required": True},
            {"accountant_review": "Yes"},
        ],
    })

    # Critical outstanding missing evidence (Stage 4.5 status vocabulary).
    OPEN_STATUSES = ["Outstanding", "Possible Match", "Accountant Review"]
    missing_critical = await db.missing_items.count_documents({
        "status": {"$in": OPEN_STATUSES},
        "priority": "Critical",
    })
    missing_total = await db.missing_items.count_documents({
        "status": {"$in": OPEN_STATUSES},
    })

    return {
        "total": total,
        "categories": categories,
        "classified": classified,
        "needs_review": needs_review,
        "missing_critical": missing_critical,
        "missing_total": missing_total,
        "duplicates": await db.upload_queue.count_documents({"status": "Duplicate?"}),
    }


@api_router.get("/dashboard/readiness")
async def dashboard_readiness():
    """Stage 5 — 'Ready for Accountant?' gate.

    READY only if every blocker is zero. Each blocker is returned with a
    count + a short human-readable reason so the UI can list them.
    """
    blockers: list[dict] = []

    # Queue still has unfinished or errored rows
    bad_q_statuses = ["Error", "Uploading", "Reading", "Classifying", "Queued"]
    for st in bad_q_statuses:
        n = await db.upload_queue.count_documents({"status": st})
        if n:
            blockers.append({"key": f"queue_{st.lower()}", "count": n,
                             "reason": f"{n} upload(s) in '{st}' state"})

    # Documents in 00 Inbox
    inbox_docs = await db.documents.count_documents({"category": "00 Inbox"})
    if inbox_docs:
        blockers.append({"key": "inbox_docs", "count": inbox_docs,
                         "reason": f"{inbox_docs} document(s) still in 00 Inbox"})

    # Accountant-review-required and not yet user-confirmed
    review_pending = await db.documents.count_documents({
        "$or": [
            {"accountant_review_required": True},
            {"accountant_review": "Yes"},
        ],
        "user_confirmed": {"$ne": True},
    })
    if review_pending:
        blockers.append({"key": "review_pending", "count": review_pending,
                         "reason": f"{review_pending} document(s) flagged for accountant review"})

    # Red-risk documents not yet user-confirmed
    red_unconfirmed = await db.documents.count_documents({
        "risk_level": "Red", "user_confirmed": {"$ne": True},
    })
    if red_unconfirmed:
        blockers.append({"key": "red_risk", "count": red_unconfirmed,
                         "reason": f"{red_unconfirmed} red-risk document(s)"})

    # Unsure tax year
    unsure_fy = await db.documents.count_documents({"tax_year": "Unsure"})
    if unsure_fy:
        blockers.append({"key": "unsure_fy", "count": unsure_fy,
                         "reason": f"{unsure_fy} document(s) with Unsure tax year"})

    # Critical outstanding missing evidence
    OPEN_STATUSES = ["Outstanding", "Possible Match", "Accountant Review"]
    crit_missing = await db.missing_items.count_documents({
        "status": {"$in": OPEN_STATUSES}, "priority": "Critical",
    })
    if crit_missing:
        blockers.append({"key": "critical_missing", "count": crit_missing,
                         "reason": f"{crit_missing} critical missing evidence item(s)"})

    return {
        "ready": len(blockers) == 0,
        "blockers": blockers,
        "checked_at": utc_now_iso(),
    }


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
        "Document ID", "SHA256", "Date uploaded", "Document name", "Original filename", "File type",
        "Tax year", "Tax year confidence", "Category", "Category confidence",
        "Document type", "Risk level", "Counterparty",
        "Date range from", "Date range to",
        "Headline figures (AI verified)", "Manual figures",
        "One-line summary", "What it proves",
        "Needs review", "Accountant review reason",
        "AI model used", "AI cost (USD)", "AI cached",
        "Storage", "Local path", "Source file available",
        "Extracted text present",
        "Google Drive folder", "Google Drive link", "Drive error",
        "Status", "User confirmed", "Notes", "User notes",
    ]
    rows = []
    for d in docs:
        manual_figs = figs_by_doc.get(d["id"], [])
        manual_text = "; ".join(f"{x.get('figure_type','')}={x.get('amount','')}" for x in manual_figs)
        ai_figs = d.get("headline_figures_json") or []
        ai_text = "; ".join(
            f"{(f.get('label') or f.get('type') or '').strip()}: {f.get('amount','')} ({f.get('confidence','') or 'unspecified'})"
            for f in ai_figs if isinstance(f, dict)
        )
        local_path = d.get("local_path") or d.get("app_storage_path") or ""
        try:
            source_available = bool(local_path) and Path(local_path).exists()
        except Exception:
            source_available = False
        rows.append([
            d.get("id", ""),
            (d.get("sha256") or "")[:64],
            d.get("created_at", ""),
            d.get("name", ""),
            d.get("original_filename", ""),
            d.get("file_type", ""),
            d.get("tax_year", ""),
            d.get("tax_year_confidence", ""),
            d.get("category", ""),
            d.get("category_confidence", ""),
            d.get("document_type", ""),
            d.get("risk_level", ""),
            d.get("counterparty", "") or "",
            d.get("date_range_from", "") or "",
            d.get("date_range_to", "") or "",
            ai_text,
            manual_text,
            d.get("one_line_summary", "") or "",
            d.get("what_it_proves", "") or "",
            "Yes" if d.get("accountant_review_required") else (d.get("accountant_review") or "No"),
            d.get("accountant_review_reason", "") or "",
            d.get("final_model_used", "") or d.get("ai_model_used", "") or "",
            f"{(d.get('total_ai_cost_usd') or d.get('ai_cost_usd') or 0):.4f}",
            "Yes" if d.get("ai_response_cached") else "No",
            d.get("storage", "") or "",
            local_path,
            "Yes" if source_available else "No",
            "Yes" if (d.get("extracted_text") or "").strip() else "No",
            d.get("drive_folder_name", ""),
            d.get("drive_link", "") or "",
            d.get("drive_error", "") or "",
            d.get("status", ""),
            "Yes" if d.get("user_confirmed") else "No",
            d.get("notes", "") or "",
            d.get("user_notes", "") or "",
        ])
    return csv_response(headers, rows, "evidence-register.csv")


@api_router.get("/reports/missing-evidence.csv")
async def export_missing():
    items = await db.missing_items.find({}, {"_id": 0}).to_list(5000)
    headers = ["Item needed", "Category", "Tax year", "Priority", "Status",
               "Matched document", "Match confidence", "Match reason", "Notes (seed)", "User notes"]
    rows = [[i.get("item_needed", ""), i.get("category", ""), i.get("tax_year", ""), i.get("priority", ""),
             i.get("status", ""), i.get("matched_document_name", "") or "", i.get("match_confidence", "") or "",
             i.get("match_reason", "") or "", i.get("notes", ""), i.get("notes_user", "") or ""] for i in items]
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


@api_router.get("/reports/accountant-summary.txt")
async def export_accountant_summary_txt():
    """Plain-text accountant summary — email-friendly companion to the PDF."""
    docs = await db.documents.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    missing = await db.missing_items.find({}, {"_id": 0}).to_list(5000)

    lines = []
    sep = "=" * 80
    dash = "-" * 80
    lines.append(sep)
    lines.append("TAX EVIDENCE VAULT — ACCOUNTANT SUMMARY")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(sep)
    lines.append("")

    # Counts by category
    cat_counts: dict[str, int] = {}
    for d in docs:
        cat_counts[d.get("category") or "Unknown"] = cat_counts.get(d.get("category") or "Unknown", 0) + 1
    lines.append(f"TOTAL DOCUMENTS: {len(docs)}")
    lines.append("")
    lines.append("DOCUMENTS BY CATEGORY:")
    lines.append(dash)
    for cat in sorted(cat_counts.keys()):
        lines.append(f"  {cat:<40s} {cat_counts[cat]:>4d}")
    lines.append("")

    # Counts by tax year
    yr_counts: dict[str, int] = {}
    for d in docs:
        yr_counts[d.get("tax_year") or "Unsure"] = yr_counts.get(d.get("tax_year") or "Unsure", 0) + 1
    lines.append("DOCUMENTS BY TAX YEAR:")
    lines.append(dash)
    for yr in sorted(yr_counts.keys()):
        lines.append(f"  {yr:<40s} {yr_counts[yr]:>4d}")
    lines.append("")

    # Risk distribution
    risk_counts = {"Green": 0, "Amber": 0, "Red": 0, "Unknown": 0}
    for d in docs:
        risk_counts[d.get("risk_level") or "Unknown"] = risk_counts.get(d.get("risk_level") or "Unknown", 0) + 1
    lines.append("AI RISK DISTRIBUTION:")
    lines.append(dash)
    for r in ["Green", "Amber", "Red", "Unknown"]:
        lines.append(f"  {r:<40s} {risk_counts.get(r, 0):>4d}")
    lines.append("")

    # Accountant review items
    review_docs = [d for d in docs if d.get("accountant_review_required") or d.get("accountant_review") == "Yes"]
    lines.append(f"ITEMS NEEDING ACCOUNTANT REVIEW: {len(review_docs)}")
    lines.append(dash)
    for d in review_docs:
        lines.append(f"  - {d.get('original_filename') or d.get('name') or ''}")
        if d.get("accountant_review_reason"):
            lines.append(f"      Reason: {d['accountant_review_reason']}")
        if d.get("category") or d.get("tax_year"):
            lines.append(f"      Category: {d.get('category','')}  Tax year: {d.get('tax_year','')}")
    lines.append("")

    # Missing evidence — outstanding, grouped by priority
    outstanding = [m for m in missing if (m.get("status") or "Outstanding") == "Outstanding"]
    by_pri = {"Critical": [], "Important": [], "Later": []}
    for m in outstanding:
        by_pri.setdefault(m.get("priority") or "Later", []).append(m)
    lines.append(f"OUTSTANDING EVIDENCE: {len(outstanding)} items")
    lines.append(dash)
    for pri in ["Critical", "Important", "Later"]:
        bucket = by_pri.get(pri, [])
        if not bucket:
            continue
        lines.append(f"  [{pri}] — {len(bucket)} items")
        for m in bucket:
            lines.append(f"    - {m.get('item_description') or m.get('item_needed') or ''}"
                         f"  ({m.get('category','')} / {m.get('tax_year','')})")
        lines.append("")

    # Possible matches awaiting review
    poss = [m for m in missing if m.get("status") == "Possible Match"]
    if poss:
        lines.append(f"POSSIBLE MATCHES — REVIEW REQUIRED: {len(poss)}")
        lines.append(dash)
        for m in poss:
            lines.append(f"  - {m.get('item_description','')}")
            if m.get("matched_document_name"):
                lines.append(f"      Matched doc: {m['matched_document_name']} ({m.get('match_confidence','')})")
            if m.get("match_reason"):
                lines.append(f"      Reason: {m['match_reason']}")
        lines.append("")

    lines.append(sep)
    lines.append("For full details, see attached:")
    lines.append("  - evidence-register.csv")
    lines.append("  - missing-evidence.csv")
    lines.append("  - accountant-summary.pdf (formatted version)")
    lines.append(sep)

    content = "\n".join(lines) + "\n"
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="accountant-summary.txt"'},
    )


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
    # Stage 4.5: outstanding ≠ legacy "status != Found". Only show items the
    # user still has work to do on.
    OPEN_STATUSES = {"Outstanding", "Possible Match", "Accountant Review"}
    open_missing = [m for m in missing if (m.get("status") or "Outstanding") in OPEN_STATUSES]
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


# =================== Stage 5: backup + final ZIP ===================

async def _build_evidence_register_csv() -> bytes:
    return (await export_evidence_register()).body  # type: ignore[attr-defined]


async def _collection_dump(collection, projection=None) -> list[dict]:
    cursor = collection.find({}, projection or {"_id": 0})
    return await cursor.to_list(20000)


@api_router.get("/reports/backup.json")
async def export_backup_json():
    """Full disaster-recovery snapshot — every collection the app owns,
    plus a generated_at timestamp. Single-user app, no auth."""
    payload = {
        "generated_at": utc_now_iso(),
        "schema_version": "stage5.v1",
        "documents":     await _collection_dump(db.documents),
        "figures":       await _collection_dump(db.figures),
        "missing_items": await _collection_dump(db.missing_items),
        "upload_queue":  await _collection_dump(db.upload_queue),
        "ai_response_cache": await _collection_dump(db.ai_response_cache),
        "ai_errors":     await _collection_dump(db.ai_errors),
        "drive_config":  await _collection_dump(db.drive_config),
        # Deliberately exclude `drive_credentials` (OAuth secrets).
    }
    body = json.dumps(payload, indent=2, default=str).encode("utf-8")
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="backup.json"'},
    )


def _safe_zip_name(s: str) -> str:
    """Strip path separators and control chars before using `s` as a zip
    entry name."""
    s = (s or "unnamed").replace("\\", "_").replace("/", "_")
    return "".join(c for c in s if c.isprintable()).strip() or "unnamed"


@api_router.get("/reports/final-accountant-pack.zip")
async def export_final_accountant_pack():
    """Stage 5 — single ZIP for the accountant containing:
      • Tax_Evidence_Export/<FY>/<category>/<filename>  (real document files)
      • evidence-register.csv, missing-evidence.csv, documents-by-category.csv
      • accountant-summary.txt, accountant-summary.pdf
      • backup.json
      • missing-source-files.txt  (only added if some files weren't on disk)
    """
    import zipfile

    docs = await db.documents.find({}, {"_id": 0}).sort("created_at", -1).to_list(10000)

    # Generate the individual report bodies by reusing the existing endpoint
    # functions. Each returns a starlette Response, so we read `.body`.
    register_resp = await export_evidence_register()
    missing_resp  = await export_missing()
    bycat_resp    = await export_by_category()
    txt_resp      = await export_accountant_summary_txt()
    pdf_resp      = await export_accountant_pdf()
    backup_resp   = await export_backup_json()

    buf = io.BytesIO()
    missing_source: list[str] = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Reports at the root
        zf.writestr("evidence-register.csv",      register_resp.body)
        zf.writestr("missing-evidence.csv",       missing_resp.body)
        zf.writestr("documents-by-category.csv",  bycat_resp.body)
        zf.writestr("accountant-summary.txt",     txt_resp.body)
        zf.writestr("accountant-summary.pdf",     pdf_resp.body)
        zf.writestr("backup.json",                backup_resp.body)

        # Documents organised under Tax_Evidence_Export/<FY>/<category>/
        # using the same canonical folder names the Drive structure uses.
        root_dir = "Tax_Evidence_Export"
        for d in docs:
            fy_raw = d.get("tax_year") or "Unsure"
            if fy_raw in ("FY2024", "FY2025"):
                fy_dir = fy_raw
            elif fy_raw in ("Both", "Historical"):
                fy_dir = fy_raw
            else:
                fy_dir = "UNKNOWN"
            cat_dir = _safe_zip_name(d.get("drive_folder_name") or d.get("category") or "00 Inbox")
            local_path = d.get("local_path") or d.get("app_storage_path") or ""
            src = Path(local_path) if local_path else None
            arc_name = _safe_zip_name(d.get("vault_filename") or d.get("original_filename") or d.get("name") or d.get("id"))
            arc_path = f"{root_dir}/{fy_dir}/{cat_dir}/{arc_name}"
            if src and src.exists():
                try:
                    zf.write(str(src), arcname=arc_path)
                except Exception as e:
                    missing_source.append(f"{arc_path}\t<read-failed: {e}>")
            else:
                missing_source.append(f"{arc_path}\t<source missing: {local_path or '(no local_path stored)'}>")

        # Always include the manifest, even if empty, so the user can verify
        # nothing was lost in flight.
        manifest = (
            "Files listed below were referenced by the evidence register but their source bytes\n"
            "weren't on disk at export time. Re-upload them to refresh the source copy.\n"
            "Tab-separated: <intended_arc_path>\\t<reason>\n\n"
        ) + ("\n".join(missing_source) if missing_source else "(none — all source files exported successfully)")
        zf.writestr("missing-source-files.txt", manifest)

    body = buf.getvalue()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    return Response(
        content=body,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="final-accountant-pack-{stamp}.zip"'},
    )


@api_router.get("/")
async def root():
    return {"app": "Tax Evidence Vault", "stage": 1}


app.include_router(api_router)

# Mount the Stage-2 bulk upload + AI pipeline router
from upload_pipeline import router as pipeline_router, init_pipeline
init_pipeline(
    db=db,
    get_drive_service=get_drive_service,
    get_or_create_folders=get_or_create_folders,
    singleton_key=SINGLETON_KEY,
)
app.include_router(pipeline_router)

# Stage 2 — Missing Evidence Tracker
import missing_evidence as me

@app.on_event("startup")
async def _seed_missing_v2():
    # Seed/refresh canonical list on every startup (idempotent)
    try:
        await me.seed_missing_evidence(db)
    except Exception as e:
        logger.warning(f"Missing evidence seed failed at startup: {e}")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    # Stage 1 PAYG preload remains (FY income figures).
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
    # Stage 2 missing-evidence seed runs in its own startup handler below.


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
