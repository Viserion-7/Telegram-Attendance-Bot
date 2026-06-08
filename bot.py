from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

from config import (
    BOT_TOKEN,
    ADMIN_ID
)

from sheets import (
    spreadsheet, employees_ws, attendance_ws, leave_ws,
    get_employee_by_telegram_id,
    already_marked_today,
    record_attendance,
    get_leave_balance,
    use_leave,
    initialize_leave_record,
    generate_monthly_report,
    get_today_report,
    reset_all_leave_balances
)

from telegram.ext import JobQueue
from datetime import time
from collections import deque
import logging
from flask import Flask, render_template_string, redirect
from threading import Thread
from datetime import datetime
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("telegram").setLevel(logging.ERROR)
logging.getLogger("telegram.ext").setLevel(logging.ERROR)

recent_logs = deque(maxlen=50)
web_app = Flask(__name__)

def bot_log(message):

    entry = {
        "time": datetime.now().isoformat(),
        "message": message
    }

    logging.info(message)
    recent_logs.append(entry)

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    telegram_id = update.effective_user.id

    employee = get_employee_by_telegram_id(
        telegram_id
    )

    if not employee:

        await update.message.reply_text(
            "❌ You are not registered in the system."
        )
        return

    initialize_leave_record(
        employee["Employee ID"]
    )

    bot_log(f"{employee['Employee']} ({employee['Employee ID']}) opened bot")

    keyboard = [
        [
            InlineKeyboardButton(
                "✅ Present",
                callback_data="present"
            )
        ],
        [
            InlineKeyboardButton(
                "🏖 Leave",
                callback_data="leave"
            )
        ],
        [
            InlineKeyboardButton(
                "📊 Balance",
                callback_data="balance"
            )
        ]
    ]

    await update.message.reply_text(
        f"Welcome {employee['Employee']} 👋\n\nLet's Mark Your Attendance:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    telegram_id = query.from_user.id

    employee = get_employee_by_telegram_id(
        telegram_id
    )

    if not employee:

        await query.edit_message_text(
            "❌ You are not registered."
        )
        return

    employee_id = employee["Employee ID"]
    employee_name = employee["Employee"]

    action = query.data

    if action == "present":

        if already_marked_today(
            employee_id
        ):

            await query.edit_message_text(
                "Attendance already marked today."
            )
            bot_log(f"{employee_name} ({employee_id}) attempted duplicate attendance")
            return

        record_attendance(
            employee_id,
            "Present"
        )
        bot_log(f"{employee_name} ({employee_id}) marked Present")

        await query.edit_message_text(
            f"✅ Attendance recorded.\n\nEmployee: {employee_name}"
        )

    elif action == "leave":

        if already_marked_today(
            employee_id
        ):

            await query.edit_message_text(
                "Attendance already marked today."
            )
            return

        success = use_leave(
            employee_id
        )

        if not success:

            await query.edit_message_text(
                "❌ No leaves remaining."
            )
            bot_log(f"{employee_name} ({employee_id}) attempted leave with no balance")
            return

        record_attendance(
            employee_id,
            "Leave"
        )

        bot_log(f"{employee_name} ({employee_id}) marked Leave")

        balance = get_leave_balance(
            employee_id
        )

        await query.edit_message_text(
            f"🏖 Leave recorded.\n\nRemaining Leaves: {balance['Remaining']}"
        )

    elif action == "balance":

        balance = get_leave_balance(
            employee_id
        )

        if not balance:

            await query.edit_message_text(
                "Leave record not found."
            )
            bot_log(f"{employee_name} ({employee_id}) requested balance for non-existent record")
            return

        bot_log(f"{employee_name} ({employee_id}) checked leave balance")

        await query.edit_message_text(
            f"""📊 Leave Summary

Employee: {employee_name}

Leaves Used: {balance['Used']}
Leaves Remaining: {balance['Remaining']}
"""
        )

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        """
Available Commands

/start - Open attendance menu
/today - Today's attendance report (Admin)
/report - Monthly attendance report (Admin)
/help - Show this message
"""
    )

async def report_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ Unauthorized"
        )
        return

    report = generate_monthly_report()
    bot_log(f"Admin {update.effective_user.id} generated monthly report")

    message = "📊 Monthly Attendance Report\n\n"

    for employee in report:

        message += (
            f"{employee['employee_id']} - "
            f"{employee['employee_name']}\n"
            f"✅ Present: {employee['present']}\n"
            f"🏖 Leave: {employee['leave']}\n"
            f"📌 Remaining: {employee['remaining']}\n\n"
        )

    await update.message.reply_text(
        message
    )

async def monthly_reset(context):

    reset_all_leave_balances()

    print("Leave balances reset.")

async def today_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ Unauthorized"
        )
        return

    report = get_today_report()
    bot_log(f"Admin {update.effective_user.id} generated today's report")

    present_count = len(
        report["present"]
    )

    leave_count = len(
        report["leave"]
    )

    message = (
        f"📅 Today's Attendance\n\n"
        f"✅ Present: {present_count}\n"
        f"🏖 Leave: {leave_count}\n\n"
    )

    message += "✅ Present Employees\n"

    if report["present"]:

        for employee in report["present"]:
            message += f"• {employee}\n"

    else:
        message += "None\n"

    message += "\n🏖 On Leave\n"

    if report["leave"]:

        for employee in report["leave"]:
            message += f"• {employee}\n"

    else:
        message += "None\n"

    await update.message.reply_text(
        message
    )

async def send_daily_reminder(context):

    employees = employees_ws.get_all_records()

    for employee in employees:

        telegram_id = employee["Telegram ID"]

        try:
            await context.bot.send_message(
                chat_id=telegram_id,
                text=(
                    "👋 Good Morning!\n\n"
                    "Please mark today's attendance.\n\n"
                    "/start"
                )
            )
        except Exception as e:
            print(e)

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logging.error(
        "Exception occurred",
        exc_info=context.error
    )

def run_web():

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    web_app.run(
        host="0.0.0.0",
        port=port
    )

@web_app.route("/")
def home():
    return redirect("/health")

@web_app.route("/health")
def health():

    logs = list(recent_logs)[-20:]

    html = """
    <html>
    <head>
        <title>Attendance Bot Health</title>

        <meta http-equiv="refresh" content="5">

        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 900px;
                margin: auto;
                padding: 20px;
                background: #f5f5f5;
            }

            h1 {
                color: #333;
            }

            .log {
                background: white;
                padding: 12px;
                margin: 8px 0;
                border-radius: 8px;
                box-shadow: 0 1px 4px rgba(0,0,0,0.1);
            }

            .time {
                color: #777;
                font-size: 12px;
            }
        </style>
    </head>

    <body>

        <h1>🤖 Attendance Bot Status</h1>

        <p>🟢 Healthy</p>

        <h2>Recent Activity</h2>

        {% for log in logs %}
        <div class="log">
            <div class="time">{{ log.time }}</div>
            <div>{{ log.message }}</div>
        </div>
        {% endfor %}

    </body>
    </html>
    """

    return render_template_string(
        html,
        logs=logs
    )

def main():

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    job_queue = app.job_queue

    job_queue.run_daily(
        send_daily_reminder,
        time=time(hour=9, minute=0)
    )

    job_queue.run_monthly(
    monthly_reset,
    when=time(hour=0, minute=0),
    day=1
)

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "help",
            help_command
        )
    )

    app.add_handler(
        CommandHandler(
            "report",
            report_command
        )
    )

    app.add_handler(
        CommandHandler(
            "today",
            today_command
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )

    Thread(
        target=run_web,
        daemon=True
    ).start()

    bot_log("Bot Started")
    app.add_error_handler(error_handler)

    app.run_polling()


if __name__ == "__main__":
    main()