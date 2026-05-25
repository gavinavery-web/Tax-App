"""Centralized upload-pipeline error codes.

Stable string codes are stored on each upload_queue row so the frontend can
render user-friendly messages and the right action button (Retry, Reconnect
Drive, Wait 60s, etc.) without sniffing free-text error strings.
"""
from __future__ import annotations


class ErrorCode:
    # File validation
    FILE_NOT_FOUND     = "FILE_NOT_FOUND"
    FILE_EMPTY         = "FILE_EMPTY"
    FILE_TOO_LARGE     = "FILE_TOO_LARGE"
    FILE_CORRUPTED     = "FILE_CORRUPTED"
    FILE_DUPLICATE     = "FILE_DUPLICATE"
    UNSUPPORTED_TYPE   = "UNSUPPORTED_TYPE"

    # Extraction
    OCR_FAILED         = "OCR_FAILED"
    EXTRACTION_FAILED  = "EXTRACTION_FAILED"
    TEXT_TOO_SHORT     = "TEXT_TOO_SHORT"

    # AI
    AI_TIMEOUT         = "AI_TIMEOUT"
    AI_RATE_LIMIT      = "AI_RATE_LIMIT"
    AI_FAILED          = "AI_FAILED"

    # Drive
    DRIVE_DISCONNECTED   = "DRIVE_DISCONNECTED"
    DRIVE_QUOTA_EXCEEDED = "DRIVE_QUOTA_EXCEEDED"
    DRIVE_UPLOAD_FAILED  = "DRIVE_UPLOAD_FAILED"

    # System
    UNEXPECTED_ERROR   = "UNEXPECTED_ERROR"
    STAGING_MISSING    = "STAGING_MISSING"
    CANCELLED          = "CANCELLED"


ERROR_MESSAGES: dict[str, str] = {
    ErrorCode.FILE_NOT_FOUND:     "File not found on server. Please re-upload.",
    ErrorCode.FILE_EMPTY:         "File is empty (0 bytes). Please check the file.",
    ErrorCode.FILE_TOO_LARGE:     "File exceeds 100 MB limit. Please compress or split the file.",
    ErrorCode.FILE_CORRUPTED:     "File appears corrupted and cannot be read.",
    ErrorCode.FILE_DUPLICATE:     "This file already exists in your evidence register.",
    ErrorCode.UNSUPPORTED_TYPE:   "File type not supported. Use PDF, JPG, PNG, DOCX, XLSX, CSV or TXT.",

    ErrorCode.OCR_FAILED:         "Could not extract text from file. Manual review may be needed.",
    ErrorCode.EXTRACTION_FAILED:  "Text extraction failed. File may be corrupted or password-protected.",
    ErrorCode.TEXT_TOO_SHORT:     "Limited text extracted. Document needs manual review.",

    ErrorCode.AI_TIMEOUT:         "AI processing timed out. Please retry.",
    ErrorCode.AI_RATE_LIMIT:      "AI rate limit reached. Please wait 60 seconds and retry.",
    ErrorCode.AI_FAILED:          "AI classification failed. Document needs manual review.",

    ErrorCode.DRIVE_DISCONNECTED:   "Google Drive disconnected. Please reconnect in Settings.",
    ErrorCode.DRIVE_QUOTA_EXCEEDED: "Google Drive storage full. Please free up space.",
    ErrorCode.DRIVE_UPLOAD_FAILED:  "Failed to upload to Google Drive. Document saved locally.",

    ErrorCode.UNEXPECTED_ERROR:   "Unexpected error occurred. Please retry or contact support.",
    ErrorCode.STAGING_MISSING:    "Temporary file missing — please re-upload.",
    ErrorCode.CANCELLED:          "Upload cancelled by user.",
}


def classify_drive_error(err: str | None) -> str:
    """Map a raw Drive exception string to a stable ErrorCode."""
    if not err:
        return ErrorCode.DRIVE_UPLOAD_FAILED
    s = err.lower()
    if "credentials" in s or "unauthorized" in s or "invalid_grant" in s or "token" in s or "401" in s or "403" in s:
        return ErrorCode.DRIVE_DISCONNECTED
    if "quota" in s or "storage" in s or "storagequotaexceeded" in s:
        return ErrorCode.DRIVE_QUOTA_EXCEEDED
    return ErrorCode.DRIVE_UPLOAD_FAILED


def classify_ai_error(err: str | None) -> str:
    """Map a raw AI exception/error string to a stable ErrorCode."""
    if not err:
        return ErrorCode.AI_FAILED
    s = err.lower()
    if "timeout" in s or "timed out" in s:
        return ErrorCode.AI_TIMEOUT
    if "429" in s or "rate limit" in s or "rate_limit" in s or "quota" in s or "overloaded" in s:
        return ErrorCode.AI_RATE_LIMIT
    return ErrorCode.AI_FAILED
