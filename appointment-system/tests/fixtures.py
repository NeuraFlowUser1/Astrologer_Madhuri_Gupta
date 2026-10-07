"""Synthetic settings only; no real account, key, receipt or connection."""

from copy import deepcopy


def installation():
    return {
        "version": 1, "installation_id": "891d05ec-8ab2-4a87-b537-1c30f2b694b6",
        "project_id": "example-practice", "label": "Example Practice",
        "environment": "test", "origin": "https://practice.example.test", "aliases": [],
        "database_targets": {purpose: {"host": "localhost", "database": "postgres",
                                     "role": role, "port": 5432, "pooling": False}
                            for purpose,role in (("web","appointment_system_web"),("staff","abs_staff"),
                            ("worker","abs_worker"),("company","abs_company"),("backup","abs_backup"),
                            ("maintenance","abs_maintenance"),("journal","abs_journal"))},
        "owners": {"client_email": "practice@example.test", "agency_email": "agency@example.test"},
        "sender": {"name": "Example Practice", "email": "booking@example.test", "reply_to": "practice@example.test"},
        "providers": {"payment": "razorpay", "calendar": "google", "email": "resend", "sms": None},
        "worker": {"name": "example-recovery", "origin": "https://worker.example.test"},
        "surfaces": [{"path": "/", "class": "general"}, {"path": "/booking", "class": "booking"}],
    }


def business(*, booking_otp=False, per_question=False):
    return {
        "version": 1, "timezone": "Asia/Kolkata",
        "services": [{"id": "consultation", "name": "Consultation", "enabled": True,
                      "duration_minutes": 30, "pricing": {"kind": "per_question" if per_question else "fixed",
                      "amount_paise": 210000, "maximum_questions": 3 if per_question else 1},
                      "required_preparation": []}],
        "weekly_windows": [{"weekday": day, "start": start, "end": end}
                           for day in range(6) for start, end in (("10:00", "12:00"), ("15:00", "18:00"))],
        "slot_step_minutes": 30, "notice_minutes": 30, "horizon_days": 10,
        "buffer_before_minutes": 0, "buffer_after_minutes": 0,
        "booking_verification": {"email": booking_otp, "sms": False},
        "required_contacts": ["email", "phone"] if booking_otp else ["phone"], "meeting": "google_meet",
        "email_budget": {"daily": 20, "rolling": 600, "verification_daily": 8, "verification_rolling": 240},
    }


def changed(document, key, value):
    result = deepcopy(document)
    result[key] = value
    return result
