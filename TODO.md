# Fix Plan

## Issue 1: Python 3.14 + Django 4.2 Compatibility
- [x] Apply monkey-patch for `BaseContext.__copy__` in `inventory_project/__init__.py`

## Issue 2: Email Verification During Registration
- [x] Create custom registration form with email field (`inventory/forms.py`)
- [x] Update registration view to create inactive user & send verification email (`inventory/views.py`)
- [x] Create email verification view (`inventory/views.py`)
- [x] Add verification URL route (`inventory/urls.py`)
- [x] Create verification templates
  - [x] `inventory/templates/email/verification_email.html`
  - [x] `inventory/templates/email/verification_email.txt`
- [x] Update register template with email field (`inventory/templates/register.html`)

