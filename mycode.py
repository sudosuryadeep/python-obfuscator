import json
import logging
from pathlib import Path
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.constants import ParseMode

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(
    "remote-bot"
)


# ============================================================
# GLOBALS
# ============================================================

BOT_USERNAME = ""

ADMIN_IDS = []

DATABASE_FILE = "bot_database.json"

FORCE_JOIN_CHANNEL = ""
FORCE_JOIN_URL = ""

DB = {}

APP = None


# ============================================================
# DATABASE
# ============================================================

def load_database():

    global DB

    path = Path(
        DATABASE_FILE
    )

    if not path.exists():

        DB = {
            "users": {},
            "settings": {
                "created_at": datetime.utcnow().isoformat()
            }
        }

        save_database()

        return

    try:

        DB = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except Exception as error:

        logger.error(
            "Database load failed: %s",
            error
        )

        DB = {
            "users": {},
            "settings": {}
        }


def save_database():

    path = Path(
        DATABASE_FILE
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temp = path.with_suffix(
        ".tmp"
    )

    temp.write_text(
        json.dumps(
            DB,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    temp.replace(path)


# ============================================================
# USER MANAGEMENT
# ============================================================

def get_user(user_id):

    user_id = str(user_id)

    if "users" not in DB:
        DB["users"] = {}

    if user_id not in DB["users"]:

        DB["users"][user_id] = {
            "id": int(user_id),
            "first_seen": datetime.utcnow().isoformat(),
            "last_seen": datetime.utcnow().isoformat(),
            "blocked": False,
        }

        save_database()

    else:

        DB["users"][user_id][
            "last_seen"
        ] = datetime.utcnow().isoformat()

    return DB["users"][user_id]


def is_admin(user_id):

    return int(user_id) in ADMIN_IDS


def is_blocked(user_id):

    user = get_user(user_id)

    return bool(
        user.get("blocked", False)
    )


# ============================================================
# KEYBOARDS
# ============================================================

def main_keyboard(user_id):

    keyboard = [
        [
            InlineKeyboardButton(
                "👤 Profile",
                callback_data="profile"
            ),
            InlineKeyboardButton(
                "ℹ️ Help",
                callback_data="help"
            ),
        ],
        [
            InlineKeyboardButton(
                "📊 Stats",
                callback_data="stats"
            ),
            InlineKeyboardButton(
                "🔄 Refresh",
                callback_data="refresh"
            ),
        ],
    ]

    if is_admin(user_id):

        keyboard.append(
            [
                InlineKeyboardButton(
                    "⚙️ Admin",
                    callback_data="admin"
                )
            ]
        )

    return InlineKeyboardMarkup(
        keyboard
    )


def back_keyboard():

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "⬅️ Back",
                    callback_data="home"
                )
            ]
        ]
    )


def admin_keyboard():

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📊 Stats",
                    callback_data="admin_stats"
                ),
                InlineKeyboardButton(
                    "👥 Users",
                    callback_data="admin_users"
                ),
            ],
            [
                InlineKeyboardButton(
                    "📢 Broadcast",
                    callback_data="admin_broadcast"
                ),
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Back",
                    callback_data="home"
                )
            ],
        ]
    )


# ============================================================
# TEXT
# ============================================================

def home_text(user):

    name = user.first_name or "User"

    return (
        "╔══════════════════════════╗\n"
        "        🤖 REMOTE BOT\n"
        "╚══════════════════════════╝\n\n"

        f"👋 Hello, <b>{name}</b>!\n\n"

        "This bot is running from the "
        "<b>remote mycode.py</b> file.\n\n"

        "Choose an option below."
    )


def help_text():

    return (
        "╔══════════════════════════╗\n"
        "          ℹ️ HELP\n"
        "╚══════════════════════════╝\n\n"

        "Available commands:\n\n"

        "• /start — Start bot\n"
        "• /help — Help menu\n"
        "• /profile — Your profile\n"
        "• /stats — Bot statistics\n\n"

        "Use the buttons for navigation."
    )


# ============================================================
# START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    if not user:
        return

    profile = get_user(
        user.id
    )

    if profile.get("blocked"):
        await update.message.reply_text(
            "🚫 Your access is blocked."
        )
        return

    await update.message.reply_text(
        home_text(user),
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(
            user.id
        ),
    )


# ============================================================
# HELP
# ============================================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        help_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=back_keyboard(),
    )


# ============================================================
# PROFILE
# ============================================================

async def profile_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    profile = get_user(
        user.id
    )

    username = (
        f"@{user.username}"
        if user.username
        else "Not set"
    )

    text = (
        "╔══════════════════════════╗\n"
        "          👤 PROFILE\n"
        "╚══════════════════════════╝\n\n"

        f"🆔 ID: <code>{user.id}</code>\n"
        f"👤 Name: {user.first_name}\n"
        f"🔗 Username: {username}\n"
        f"📅 Joined: {profile.get('first_seen', 'Unknown')}\n"
    )

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=back_keyboard(),
    )


# ============================================================
# STATS
# ============================================================

async def stats_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    users = DB.get(
        "users",
        {}
    )

    total = len(users)

    blocked = sum(
        1
        for user in users.values()
        if user.get("blocked")
    )

    active = total - blocked

    text = (
        "╔══════════════════════════╗\n"
        "          📊 STATS\n"
        "╚══════════════════════════╝\n\n"

        f"👥 Total Users: <b>{total}</b>\n"
        f"🟢 Active Users: <b>{active}</b>\n"
        f"🔴 Blocked Users: <b>{blocked}</b>\n"
    )

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=back_keyboard(),
    )


# ============================================================
# CALLBACK HANDLER
# ============================================================

async def callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    user = query.from_user

    data = query.data

    # --------------------------------------------------------
    # HOME
    # --------------------------------------------------------

    if data == "home":

        await query.edit_message_text(
            home_text(user),
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(
                user.id
            ),
        )

        return

    # --------------------------------------------------------
    # PROFILE
    # --------------------------------------------------------

    if data == "profile":

        profile = get_user(
            user.id
        )

        username = (
            f"@{user.username}"
            if user.username
            else "Not set"
        )

        text = (
            "╔══════════════════════════╗\n"
            "          👤 PROFILE\n"
            "╚══════════════════════════╝\n\n"

            f"🆔 ID: <code>{user.id}</code>\n"
            f"👤 Name: {user.first_name}\n"
            f"🔗 Username: {username}\n"
            f"📅 Joined: {profile.get('first_seen', 'Unknown')}"
        )

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard(),
        )

        return

    # --------------------------------------------------------
    # HELP
    # --------------------------------------------------------

    if data == "help":

        await query.edit_message_text(
            help_text(),
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard(),
        )

        return

    # --------------------------------------------------------
    # STATS
    # --------------------------------------------------------

    if data == "stats":

        users = DB.get(
            "users",
            {}
        )

        total = len(users)

        blocked = sum(
            1
            for u in users.values()
            if u.get("blocked")
        )

        active = total - blocked

        text = (
            "╔══════════════════════════╗\n"
            "          📊 STATS\n"
            "╚══════════════════════════╝\n\n"

            f"👥 Total: <b>{total}</b>\n"
            f"🟢 Active: <b>{active}</b>\n"
            f"🔴 Blocked: <b>{blocked}</b>"
        )

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard(),
        )

        return

    # --------------------------------------------------------
    # REFRESH
    # --------------------------------------------------------

    if data == "refresh":

        get_user(
            user.id
        )

        await query.edit_message_text(
            home_text(user),
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(
                user.id
            ),
        )

        return

    # --------------------------------------------------------
    # ADMIN
    # --------------------------------------------------------

    if data == "admin":

        if not is_admin(user.id):

            await query.answer(
                "🚫 Admin only.",
                show_alert=True
            )

            return

        await query.edit_message_text(
            "╔══════════════════════════╗\n"
            "          ⚙️ ADMIN\n"
            "╚══════════════════════════╝\n\n"
            "Select an option:",
            reply_markup=admin_keyboard(),
        )

        return

    # --------------------------------------------------------
    # ADMIN STATS
    # --------------------------------------------------------

    if data == "admin_stats":

        if not is_admin(user.id):
            return

        users = DB.get(
            "users",
            {}
        )

        total = len(users)

        blocked = sum(
            1
            for u in users.values()
            if u.get("blocked")
        )

        text = (
            "📊 <b>ADMIN STATISTICS</b>\n\n"
            f"👥 Users: <b>{total}</b>\n"
            f"🟢 Active: <b>{total - blocked}</b>\n"
            f"🔴 Blocked: <b>{blocked}</b>"
        )

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard(),
        )

        return

    # --------------------------------------------------------
    # ADMIN USERS
    # --------------------------------------------------------

    if data == "admin_users":

        if not is_admin(user.id):
            return

        users = DB.get(
            "users",
            {}
        )

        text = (
            "👥 <b>USERS</b>\n\n"
            f"Total registered: <b>{len(users)}</b>"
        )

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard(),
        )

        return

    # --------------------------------------------------------
    # BROADCAST
    # --------------------------------------------------------

    if data == "admin_broadcast":

        if not is_admin(user.id):
            return

        context.user_data[
            "broadcast_mode"
        ] = True

        await query.edit_message_text(
            "📢 <b>Broadcast Mode</b>\n\n"
            "Send the message you want to broadcast.\n\n"
            "Use /cancel to cancel.",
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard(),
        )

        return


# ============================================================
# BROADCAST MESSAGE
# ============================================================

async def message_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    if not user:
        return

    if not is_admin(user.id):
        return

    if not context.user_data.get(
        "broadcast_mode"
    ):
        return

    context.user_data[
        "broadcast_mode"
    ] = False

    users = DB.get(
        "users",
        {}
    )

    sent = 0
    failed = 0

    status = await update.message.reply_text(
        "📢 Starting broadcast..."
    )

    for user_id, profile in users.items():

        if profile.get("blocked"):
            continue

        try:

            await context.bot.copy_message(
                chat_id=int(user_id),
                from_chat_id=update.effective_chat.id,
                message_id=update.message.message_id,
            )

            sent += 1

        except Exception as error:

            failed += 1

            logger.warning(
                "Broadcast failed for %s: %s",
                user_id,
                error
            )

    await status.edit_text(
        "📢 <b>Broadcast Completed</b>\n\n"
        f"✅ Sent: <b>{sent}</b>\n"
        f"❌ Failed: <b>{failed}</b>",
        parse_mode=ParseMode.HTML,
    )


# ============================================================
# CANCEL
# ============================================================

async def cancel_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    context.user_data[
        "broadcast_mode"
    ] = False

    await update.message.reply_text(
        "❌ Cancelled.",
        reply_markup=main_keyboard(
            update.effective_user.id
        ),
    )


# ============================================================
# CREATE BOT
# ============================================================

def create_bot(token, config):

    global BOT_USERNAME
    global ADMIN_IDS
    global DATABASE_FILE
    global FORCE_JOIN_CHANNEL
    global FORCE_JOIN_URL
    global APP

    # --------------------------------------------------------
    # CONFIG
    # --------------------------------------------------------

    BOT_USERNAME = config.get(
        "bot_username",
        ""
    )

    ADMIN_IDS = config.get(
        "admin_ids",
        []
    )

    DATABASE_FILE = config.get(
        "database_file",
        "bot_database.json"
    )

    FORCE_JOIN_CHANNEL = config.get(
        "force_join_channel",
        ""
    )

    FORCE_JOIN_URL = config.get(
        "force_join_url",
        ""
    )

    # --------------------------------------------------------
    # DATABASE
    # --------------------------------------------------------

    load_database()

    # --------------------------------------------------------
    # APPLICATION
    # --------------------------------------------------------

    APP = (
        Application
        .builder()
        .token(token)
        .build()
    )

    # --------------------------------------------------------
    # COMMANDS
    # --------------------------------------------------------

    APP.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    APP.add_handler(
        CommandHandler(
            "help",
            help_command
        )
    )

    APP.add_handler(
        CommandHandler(
            "profile",
            profile_command
        )
    )

    APP.add_handler(
        CommandHandler(
            "stats",
            stats_command
        )
    )

    APP.add_handler(
        CommandHandler(
            "cancel",
            cancel_command
        )
    )

    # --------------------------------------------------------
    # CALLBACKS
    # --------------------------------------------------------

    APP.add_handler(
        CallbackQueryHandler(
            callback_handler
        )
    )

    # --------------------------------------------------------
    # NORMAL TEXT / BROADCAST
    # --------------------------------------------------------

    APP.add_handler(
        MessageHandler(
            filters.ALL
            & ~filters.COMMAND,
            message_handler
        )
    )

    logger.info(
        "Remote bot application created"
    )

    return APP
