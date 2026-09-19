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

ADMIN_IDS = [8256108006]

DATABASE_FILE = "bot_database.json"

FORCE_JOIN_CHANNEL = ""
FORCE_JOIN_URL = ""

DB = {}

APP = None


# ============================================================
# FILE MANAGER
# ============================================================

# Starting directory is the directory from which the bot process
# was started. The admin cannot navigate outside this directory.
FILE_ROOT = Path.cwd().resolve()

# Maximum number of entries shown in one directory.
MAX_FILE_ENTRIES = 40

# Maximum Telegram document size depends on Telegram/account/API
# limitations. This is only a local safety limit.
MAX_FILE_SIZE = 50 * 1024 * 1024


def get_safe_path(relative_path="."):
    """
    Convert an admin file-browser path into an absolute path while
    ensuring it remains inside FILE_ROOT.
    """

    try:
        root = FILE_ROOT.resolve()

        candidate = (
            FILE_ROOT / relative_path
        ).resolve()

        try:
            candidate.relative_to(root)
        except ValueError:
            return None

        return candidate

    except Exception:
        return None


def get_relative_path(path):
    """
    Return path relative to FILE_ROOT.
    """

    try:
        return path.resolve().relative_to(
            FILE_ROOT
        )
    except Exception:
        return Path(".")


def file_browser_keyboard(current_path, entries):
    """
    Build the inline keyboard for the current directory.
    """

    keyboard = []

    for index, entry in enumerate(entries):

        if entry.is_dir():

            label = f"📁 {entry.name}"

        else:

            try:
                size = entry.stat().st_size

                if size < 1024:
                    size_text = f"{size} B"

                elif size < 1024 * 1024:
                    size_text = f"{size / 1024:.1f} KB"

                else:
                    size_text = (
                        f"{size / (1024 * 1024):.1f} MB"
                    )

            except Exception:

                size_text = "?"

            label = (
                f"📄 {entry.name} "
                f"({size_text})"
            )

        keyboard.append(
            [
                InlineKeyboardButton(
                    label[:60],
                    callback_data=f"fm:item:{index}",
                )
            ]
        )

    relative = get_relative_path(
        current_path
    )

    if relative == Path("."):

        path_text = "📍 /"

    else:

        path_text = (
            "📍 /"
            + str(relative).replace("\\", "/")
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                "⬆️ Up",
                callback_data="fm:up",
            ),
            InlineKeyboardButton(
                "🏠 Root",
                callback_data="fm:root",
            ),
        ]
    )

    keyboard.append(
        [
            InlineKeyboardButton(
                "🔄 Refresh",
                callback_data="fm:refresh",
            ),
            InlineKeyboardButton(
                "⬅️ Admin",
                callback_data="admin",
            ),
        ]
    )

    return (
        InlineKeyboardMarkup(keyboard),
        path_text,
    )


def get_directory_entries(path):
    """
    Return directories first, then files.
    """

    try:

        entries = list(path.iterdir())

    except Exception as error:

        logger.warning(
            "Unable to list directory %s: %s",
            path,
            error,
        )

        return []

    directories = []
    files = []

    for entry in entries:

        try:

            # Ignore broken symlinks and inaccessible entries.
            if entry.is_symlink():

                # Resolve and verify the symlink target.
                resolved = entry.resolve()

                try:
                    resolved.relative_to(
                        FILE_ROOT
                    )
                except ValueError:
                    continue

            if entry.is_dir():

                directories.append(entry)

            elif entry.is_file():

                files.append(entry)

        except Exception:

            continue

    directories.sort(
        key=lambda x: x.name.lower()
    )

    files.sort(
        key=lambda x: x.name.lower()
    )

    return (
        directories + files
    )[:MAX_FILE_ENTRIES]


def file_browser_text(path, entries):
    """
    Create the text shown above the file browser keyboard.
    """

    relative = get_relative_path(
        path
    )

    if relative == Path("."):

        display_path = "/"

    else:

        display_path = (
            "/"
            + str(relative).replace("\\", "/")
        )

    directories = sum(
        1
        for entry in entries
        if entry.is_dir()
    )

    files = sum(
        1
        for entry in entries
        if entry.is_file()
    )

    return (
        "╔══════════════════════════╗\n"
        "          📁 FILES\n"
        "╚══════════════════════════╝\n\n"
        f"📍 <code>{display_path}</code>\n\n"
        f"📁 Folders: <b>{directories}</b>\n"
        f"📄 Files: <b>{files}</b>\n\n"
        "Select a folder to open it, "
        "or select a file to send it."
    )


async def show_file_browser(
    query,
    context,
    path=None,
):
    """
    Display the file browser for an admin.
    """

    user = query.from_user

    if not is_admin(user.id):

        await query.answer(
            "🚫 Admin only.",
            show_alert=True,
        )

        return

    if path is None:

        path = FILE_ROOT

    path = get_safe_path(
        get_relative_path(path)
    )

    if path is None or not path.is_dir():

        await query.answer(
            "❌ Invalid directory.",
            show_alert=True,
        )

        return

    # Store current directory for this admin.
    context.user_data[
        "file_browser_path"
    ] = str(
        get_relative_path(path)
    )

    entries = get_directory_entries(
        path
    )

    # Store entries so callback buttons only need
    # a small numeric callback_data value.
    context.user_data[
        "file_browser_entries"
    ] = [
        entry.name
        for entry in entries
    ]

    text = file_browser_text(
        path,
        entries,
    )

    keyboard, _ = file_browser_keyboard(
        path,
        entries,
    )

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


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
                    "📁 Files",
                    callback_data="file_manager"
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
        f"📅 Joined: "
        f"{profile.get('first_seen', 'Unknown')}\n"
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
    # FILE MANAGER
    # --------------------------------------------------------

    if data == "file_manager":

        if not is_admin(user.id):

            await query.answer(
                "🚫 Admin only.",
                show_alert=True,
            )

            return

        await show_file_browser(
            query,
            context,
            FILE_ROOT,
        )

        return


    # --------------------------------------------------------
    # FILE MANAGER - ROOT
    # --------------------------------------------------------

    if data == "fm:root":

        if not is_admin(user.id):
            return

        await show_file_browser(
            query,
            context,
            FILE_ROOT,
        )

        return


    # --------------------------------------------------------
    # FILE MANAGER - UP
    # --------------------------------------------------------

    if data == "fm:up":

        if not is_admin(user.id):
            return

        relative = context.user_data.get(
            "file_browser_path",
            ".",
        )

        current = get_safe_path(
            relative
        )

        if current is None:
            current = FILE_ROOT

        if current == FILE_ROOT:

            parent = FILE_ROOT

        else:

            parent = current.parent

            try:

                parent.relative_to(
                    FILE_ROOT
                )

            except ValueError:

                parent = FILE_ROOT

        await show_file_browser(
            query,
            context,
            parent,
        )

        return


    # --------------------------------------------------------
    # FILE MANAGER - REFRESH
    # --------------------------------------------------------

    if data == "fm:refresh":

        if not is_admin(user.id):
            return

        relative = context.user_data.get(
            "file_browser_path",
            ".",
        )

        current = get_safe_path(
            relative
        )

        if current is None or not current.is_dir():

            current = FILE_ROOT

        await show_file_browser(
            query,
            context,
            current,
        )

        return


    # --------------------------------------------------------
    # FILE MANAGER - ITEM
    # --------------------------------------------------------

    if data.startswith("fm:item:"):

        if not is_admin(user.id):
            return

        try:

            index = int(
                data.split(":")[-1]
            )

        except ValueError:

            await query.answer(
                "❌ Invalid item.",
                show_alert=True,
            )

            return

        relative = context.user_data.get(
            "file_browser_path",
            ".",
        )

        current = get_safe_path(
            relative
        )

        if current is None or not current.is_dir():

            await query.answer(
                "❌ Directory no longer exists.",
                show_alert=True,
            )

            return

        entries = get_directory_entries(
            current
        )

        if index < 0 or index >= len(entries):

            await query.answer(
                "❌ Item no longer exists.",
                show_alert=True,
            )

            return

        selected = entries[index]

        # Re-resolve and verify the selected path.
        try:

            selected = selected.resolve()

            selected.relative_to(
                FILE_ROOT
            )

        except Exception:

            await query.answer(
                "🚫 Access denied.",
                show_alert=True,
            )

            return


        # ----------------------------------------------------
        # DIRECTORY
        # ----------------------------------------------------

        if selected.is_dir():

            await show_file_browser(
                query,
                context,
                selected,
            )

            return


        # ----------------------------------------------------
        # FILE
        # ----------------------------------------------------

        if selected.is_file():

            try:

                size = selected.stat().st_size

            except Exception:

                await query.answer(
                    "❌ Unable to read file.",
                    show_alert=True,
                )

                return

            if size > MAX_FILE_SIZE:

                await query.answer(
                    "❌ File is too large.",
                    show_alert=True,
                )

                return

            await query.answer(
                "📤 Sending file..."
            )

            try:

                relative_file = get_relative_path(
                    selected
                )

                caption = (
                    "📄 <b>File</b>\n\n"
                    f"📍 <code>/"
                    f"{str(relative_file).replace(chr(92), '/')}"
                    f"</code>\n"
                    f"📦 Size: <b>"
                    f"{size / (1024 * 1024):.2f} MB"
                    f"</b>"
                )

                with selected.open(
                    "rb"
                ) as document:

                    await context.bot.send_document(
                        chat_id=user.id,
                        document=document,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                    )

            except Exception as error:

                logger.exception(
                    "Failed to send file: %s",
                    error,
                )

                await context.bot.send_message(
                    chat_id=user.id,
                    text=(
                        "❌ <b>Failed to send file.</b>\n\n"
                        f"<code>{error}</code>"
                    ),
                    parse_mode=ParseMode.HTML,
                )

            return


        await query.answer(
            "❌ Unsupported item.",
            show_alert=True,
        )

        return


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
            f"📅 Joined: "
            f"{profile.get('first_seen', 'Unknown')}"
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

def create_bot(token, config=None):

    global BOT_USERNAME
    global ADMIN_IDS
    global DATABASE_FILE
    global FORCE_JOIN_CHANNEL
    global FORCE_JOIN_URL
    global APP

    # --------------------------------------------------------
    # CONFIG
    # --------------------------------------------------------

    config = config or {}

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
    # FILE MANAGER ROOT
    # --------------------------------------------------------

    global FILE_ROOT

    FILE_ROOT = Path.cwd().resolve()

    logger.info(
        "File manager root: %s",
        FILE_ROOT
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
