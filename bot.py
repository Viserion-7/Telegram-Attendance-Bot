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
            return

        record_attendance(
            employee_id,
            "Present"
        )

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
            return

        record_attendance(
            employee_id,
            "Leave"
        )

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
            return

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

    print("Bot Started...")

    app.run_polling()


if __name__ == "__main__":
    main()