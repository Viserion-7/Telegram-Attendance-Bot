from google.oauth2.service_account import Credentials
import gspread

from config import SPREADSHEET_ID
from datetime import date, datetime
from collections import defaultdict

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets"
]
import json
import os

creds_info = json.loads(
    os.environ["GOOGLE_CREDENTIALS"]
)

creds = Credentials.from_service_account_info(
    creds_info,
    scopes=SCOPES
)

client = gspread.authorize(creds)

spreadsheet = client.open_by_key(SPREADSHEET_ID)

employees_ws = spreadsheet.worksheet("Employees")
attendance_ws = spreadsheet.worksheet("Attendance")
leave_ws = spreadsheet.worksheet("Leave Summary")


def get_employee_by_telegram_id(telegram_id):

    records = employees_ws.get_all_records()

    for row in records:

        if str(row["Telegram ID"]) == str(telegram_id):
            return row

    return None


def already_marked_today(employee_id):

    today = str(date.today())

    records = attendance_ws.get_all_records()

    for row in records:

        if (
            row["Date"] == today
            and str(row["Employee ID"]) == str(employee_id)
        ):
            return True

    return False


def record_attendance(employee_id, status):

    attendance_ws.append_row(
        [
            str(date.today()),
            employee_id,
            status,
            datetime.now().isoformat()
        ]
    )


def get_leave_balance(employee_id):

    records = leave_ws.get_all_records()

    for row in records:

        if str(row["Employee ID"]) == str(employee_id):
            return row

    return None


def use_leave(employee_id):

    records = leave_ws.get_all_records()

    for index, row in enumerate(records, start=2):

        if str(row["Employee ID"]) == str(employee_id):

            used = int(row["Used"])
            remaining = int(row["Remaining"])

            if remaining <= 0:
                return False

            leave_ws.update(
                f"B{index}:C{index}",
                [[used + 1, remaining - 1]]
            )

            return True

    return False


def initialize_leave_record(employee_id):

    existing = get_leave_balance(employee_id)

    if existing:
        return

    leave_ws.append_row(
        [
            employee_id,
            0,
            4
        ]
    )


def get_today_report():

    today = str(date.today())

    attendance_records = attendance_ws.get_all_records()
    employees = employees_ws.get_all_records()

    employee_lookup = {
        row["Employee ID"]: row["Employee"]
        for row in employees
    }

    present = []
    leave = []

    for row in attendance_records:

        if row["Date"] != today:
            continue

        employee_id = row["Employee ID"]

        employee_name = employee_lookup.get(
            employee_id,
            employee_id
        )

        if row["Status"] == "Present":
            present.append(employee_name)

        elif row["Status"] == "Leave":
            leave.append(employee_name)

    return {
        "present": present,
        "leave": leave
    }


def generate_monthly_report():

    attendance_records = attendance_ws.get_all_records()
    employees = employees_ws.get_all_records()
    leave_records = leave_ws.get_all_records()

    report = []

    leave_lookup = {}

    for row in leave_records:
        leave_lookup[row["Employee ID"]] = row

    attendance_summary = defaultdict(
        lambda: {
            "Present": 0,
            "Leave": 0
        }
    )

    for row in attendance_records:

        employee_id = row["Employee ID"]
        status = row["Status"]

        if status == "Present":
            attendance_summary[employee_id]["Present"] += 1

        elif status == "Leave":
            attendance_summary[employee_id]["Leave"] += 1

    for employee in employees:

        employee_id = employee["Employee ID"]

        leave_data = leave_lookup.get(
            employee_id,
            {"Remaining": 4}
        )

        report.append({
            "employee_id": employee_id,
            "employee_name": employee["Employee"],
            "present": attendance_summary[employee_id]["Present"],
            "leave": attendance_summary[employee_id]["Leave"],
            "remaining": leave_data["Remaining"]
        })

    return report

def reset_all_leave_balances():

    records = leave_ws.get_all_records()

    for index, row in enumerate(records, start=2):

        leave_ws.update(
            f"B{index}:C{index}",
            [[0, 4]]
        )