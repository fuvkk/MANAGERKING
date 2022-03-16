import datetime
import importlib
import re
import resource
import platform
import sys
import traceback
import wikipedia
from typing import Optional, List

from telegram import Message, Chat, Update, Bot, User
from telegram import ParseMode, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import Unauthorized, BadRequest, TimedOut, NetworkError, ChatMigrated, TelegramError
from telegram.ext import CommandHandler, Filters, MessageHandler, CallbackQueryHandler
from telegram.ext.dispatcher import run_async, DispatcherHandlerStop, Dispatcher
from telegram.utils.helpers import escape_markdown, mention_html

from emilia import dispatcher, updater, TOKEN, WEBHOOK, OWNER_USERNAME, OWNER_ID, DONATION_LINK, CERT_PATH, PORT, URL, LOGGER, spamcheck
from emilia.vars import BOT
# needed to dynamically load modules
# NOTE: Module order is not guaranteed, specify that in the config file!
from emilia.modules import ALL_MODULES
from emilia.modules.languages import tl
from emilia.modules.helper_funcs.chat_status import is_user_admin
from emilia.modules.helper_funcs.misc import paginate_modules
from emilia.modules.helper_funcs.verifier import verify_welcome
from emilia.modules.sql import languages_sql as langsql

from emilia.modules.connection import connect_button
from emilia.modules.languages import set_language

PM_START_TEXT = "start_text"

HELP_STRINGS = "help_text" # format(dispatcher.bot.first_name, "" if not ALLOW_EXCL else "\nAll commands can either be used with / or !.\n")


IMPORTED = {}
MIGRATEABLE = []
HELPABLE = {}
STATS = []
USER_INFO = []
DATA_IMPORT = []
DATA_EXPORT = []

CHAT_SETTINGS = {}
USER_SETTINGS = {}

for module_name in ALL_MODULES:
    imported_module = importlib.import_module("emilia.modules." + module_name)
    if not hasattr(imported_module, "__mod_name__"):
        imported_module.__mod_name__ = imported_module.__name__

    if not imported_module.__mod_name__.lower() in IMPORTED:
        IMPORTED[imported_module.__mod_name__.lower()] = imported_module
    else:
        raise Exception("Can't have two modules with the same name! Please change one")

    if hasattr(imported_module, "__help__") and imported_module.__help__:
        HELPABLE[imported_module.__mod_name__.lower()] = imported_module

    # Chats to migrate on chat_migrated events
    if hasattr(imported_module, "__migrate__"):
        MIGRATEABLE.append(imported_module)

    if hasattr(imported_module, "__stats__"):
        STATS.append(imported_module)

    if hasattr(imported_module, "__user_info__"):
        USER_INFO.append(imported_module)

    if hasattr(imported_module, "__import_data__"):
        DATA_IMPORT.append(imported_module)

    if hasattr(imported_module, "__export_data__"):
        DATA_EXPORT.append(imported_module)

    if hasattr(imported_module, "__chat_settings__"):
        CHAT_SETTINGS[imported_module.__mod_name__.lower()] = imported_module

    if hasattr(imported_module, "__user_settings__"):
        USER_SETTINGS[imported_module.__mod_name__.lower()] = imported_module

# do not async
def send_help(chat_id, text, keyboard=None):
    if not keyboard:
        keyboard = InlineKeyboardMarkup(paginate_modules(0, HELPABLE, "help"))
    dispatcher.bot.send_message(chat_id=chat_id,
                                text=text,
                                parse_mode=ParseMode.MARKDOWN,
                                reply_markup=keyboard)


@run_async
def test(update, context):
    # pprint(eval(str(update)))
    # update.effective_message.reply_text("Hola tester! _I_ *have* `markdown`", parse_mode=ParseMode.MARKDOWN)
    update.effective_message.reply_text("This person edited a message")
    print(context.match)
    print(update.effective_message.text)


@run_async
@spamcheck
def start(update, context):
    if update.effective_chat.type == "private":
        args = context.args
        if len(args) >= 1:
            if args[0].lower() == "help":
                send_help(update.effective_chat.id, tl(update.effective_message, HELP_STRINGS))

            elif args[0].lower() == "get_notes":
                update.effective_message.reply_text(tl(update.effective_message, "Now you can get notes in group."))

            elif args[0].lower().startswith("stngs_"):
                match = re.match("stngs_(.*)", args[0].lower())
                chat = dispatcher.bot.getChat(match.group(1))

                if is_user_admin(chat, update.effective_user.id):
                    send_settings(match.group(1), update.effective_user.id, False)
                else:
                    send_settings(match.group(1), update.effective_user.id, True)

            elif args[0][1:].isdigit() and "rules" in IMPORTED:
                IMPORTED["rules"].send_rules(update, args[0], from_pm=True)

            elif args[0][:4] == "wiki":
                wiki = args[0].split("-")[1].replace('_', ' ')
                message = update.effective_message
                getlang = langsql.get_lang(message)
                if getlang == "id":
                    wikipedia.set_lang("id")
                pagewiki = wikipedia.page(wiki)
                judul = pagewiki.title
                summary = pagewiki.summary
                if len(summary) >= 4096:
                    summary = summary[:4000]+"..."
                message.reply_text("<b>{}</b>\n{}".format(judul, summary), parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(
                            [[InlineKeyboardButton(text=tl(update.effective_message, "Read on Wikipedia"), url=pagewiki.url)]]))

            elif args[0][:6].lower() == "verify":
                chat_id = args[0].split("_")[1]
                verify_welcome(update, context, chat_id)

            elif args[0][:6].lower() == "verify":
                chat_id = args[0].split("_")[1]
                verify_welcome(update, context, chat_id)

        else:
            first_name = update.effective_user.first_name
            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton(text="Connect 🔐", callback_data="aboutmanu_"),
                 InlineKeyboardButton(text="Language 🌎", callback_data="main_setlang")], [InlineKeyboardButton(text="Commands 📋", callback_data="help_back"),
                 InlineKeyboardButton(text="About 👨🏻‍💻", callback_data="aboutmanu_cbguide")],
                [InlineKeyboardButton(text="✚ Add Bot in Your Group ✚", url=f"https://t.me/{BOT}?startgroup=new")]])
            update.effective_message.reply_text(
                tl(update.effective_message, PM_START_TEXT).format(escape_markdown(first_name), escape_markdown(context.bot.first_name), OWNER_USERNAME),
                disable_web_page_preview=True,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=buttons)
    else:
        update.effective_message.reply_text(tl(update.effective_message, "Ada yang bisa saya bantu? 😊"))


def m_connect_button(update, context):
    context.bot.delete_message(update.effective_chat.id, update.effective_message.message_id)
    connect_button(update, context)

def m_change_langs(update, context):
    context.bot.delete_message(update.effective_chat.id, update.effective_message.message_id)
    set_language(update, context)

# for test purposes
def error_callback(update, context):
    # add all the dev user_ids in this list. You can also add ids of channels or groups.
    devs = [OWNER_ID]
    # we want to notify the user of this problem. This will always work, but not notify users if the update is an 
    # callback or inline query, or a poll update. In case you want this, keep in mind that sending the message 
    # could fail
    if update.effective_message:
        text = "Hey. I'm sorry to inform you that an error happened while I tried to handle your update. " \
               "My developer(s) will be notified."
        update.effective_message.reply_text(text)
    # This traceback is created with accessing the traceback object from the sys.exc_info, which is returned as the
    # third value of the returned tuple. Then we use the traceback.format_tb to get the traceback as a string, which
    # for a weird reason separates the line breaks in a list, but keeps the linebreaks itself. So just joining an
    # empty string works fine.
    trace = "".join(traceback.format_tb(sys.exc_info()[2]))
    # lets try to get as much information from the telegram update as possible
    payload = ""
    # normally, we always have an user. If not, its either a channel or a poll update.
    if update.effective_user:
        payload += f' with the user {mention_html(update.effective_user.id, update.effective_user.first_name)}'
    # there are more situations when you don't get a chat
    if update.effective_chat:
        payload += f' within the chat <i>{update.effective_chat.title}</i>'
        if update.effective_chat.username:
            payload += f' (@{update.effective_chat.username})'
    # but only one where you have an empty payload by now: A poll (buuuh)
    if update.poll:
        payload += f' with the poll id {update.poll.id}.'
    # lets put this in a "well" formatted text
    text = f"Hey.\n The error <code>{context.error}</code> happened{payload}. The full traceback:\n\n<code>{trace}" \
           f"</code>"
    # and send it to the dev(s)
    for dev_id in devs:
        context.bot.send_message(dev_id, text, parse_mode=ParseMode.HTML)
    # we raise the error again, so the logger module catches it. If you don't use the logger module, use it.
    try:
        raise context.error
    except Unauthorized:
        # remove update.message.chat_id from conversation list
        LOGGER.exception('Update "%s" caused error "%s"', update, context.error)
    except BadRequest:
        # handle malformed requests - read more below!
        LOGGER.exception('Update "%s" caused error "%s"', update, context.error)
    except TimedOut:
        # handle slow connection problems
        LOGGER.exception('Update "%s" caused error "%s"', update, context.error)
    except NetworkError:
        # handle other connection problems
        LOGGER.exception('Update "%s" caused error "%s"', update, context.error)
    except ChatMigrated as e:
        # the chat_id of a group has changed, use e.new_chat_id instead
        LOGGER.exception('Update "%s" caused error "%s"', update, context.error)
    except TelegramError:
        # handle all other telegram related errors
        LOGGER.exception('Update "%s" caused error "%s"', update, context.error)


@run_async
def help_button(update, context):
    query = update.callback_query
    mod_match = re.match(r"help_module\((.+?)\)", query.data)
    prev_match = re.match(r"help_prev\((.+?)\)", query.data)
    next_match = re.match(r"help_next\((.+?)\)", query.data)
    back_match = re.match(r"help_back", query.data)

    print(query.message.chat.id)

    try:
        if mod_match:
            module = mod_match.group(1)
            text = tl(update.effective_message, "Ini bantuan untuk modul *{}*:\n").format(HELPABLE[module].__mod_name__) \
                   + tl(update.effective_message, HELPABLE[module].__help__)

            query.message.edit_text(text=text,
                                  parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=InlineKeyboardMarkup(
                                        [[InlineKeyboardButton(text=tl(query.message, "⬅️ kembali"), callback_data="help_back")]]))

        elif prev_match:
            curr_page = int(prev_match.group(1))
            query.message.edit_text(text=tl(query.message, HELP_STRINGS),
                                  parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=InlineKeyboardMarkup(
                                        paginate_modules(curr_page - 1, HELPABLE, "help")))

        elif next_match:
            next_page = int(next_match.group(1))
            query.message.edit_text(text=tl(query.message, HELP_STRINGS),
                                  parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=InlineKeyboardMarkup(
                                        paginate_modules(next_page + 1, HELPABLE, "help")))

        elif back_match:
            query.message.edit_text(text=tl(query.message, HELP_STRINGS),
                                  parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=InlineKeyboardMarkup(paginate_modules(0, HELPABLE, "help")))


        context.bot.answer_callback_query(query.id)
    except Exception as excp:
        if excp.message == "Message is not modified":
            pass
        elif excp.message == "Query_id_invalid":
            pass
        elif excp.message == "Message can't be deleted":
            pass
        else:
            query.message.edit_text(excp.message)
            LOGGER.exception("Exception in help buttons. %s", str(query.data))


def aries_about_callback(update, context):
    query = update.callback_query
    if query.data == "aboutmanu_":
        query.message.edit_text(
            text=f"*👋 ʜʟᴏ ᴍʏ ɴᴀᴍᴇ ɪꜱ ᴄʀᴇᴀᴛᴏʀ ᴘᴀᴠᴀɴ.\n\nᴀ ᴘᴏᴡᴇʀꜰᴜʟ ɢʀᴏᴜᴘ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ ʙᴏᴛ ʙᴜɪʟᴛ ᴛᴏ ʜᴇʟᴘ ʏᴏᴜ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ɢʀᴏᴜᴘ ᴇᴀꜱɪʟʏ ᴀɴᴅ ᴛᴏ ᴘʀᴏᴛᴇᴄᴛ ʏᴏᴜʀ ɢʀᴏᴜᴘ ꜰʀᴏᴍ ꜱᴄᴀᴍᴍᴇʀꜱ ᴀɴᴅ ꜱᴘᴀᴍᴍᴇʀꜱ.* "
            f"\n\nɪ ʜᴀᴠᴇ ᴛʜᴇ ɴᴏʀᴍᴀʟ ɢʀᴏᴜᴘ ᴍᴀɴᴀɢɪɴɢ ꜰᴜɴᴄᴛɪᴏɴꜱ ʟɪᴋᴇ ꜰʟᴏᴏᴅ ᴄᴏɴᴛʀᴏʟ, ᴀ ᴡᴀʀɴɪɴɢ ꜱʏꜱᴛᴇᴍ ᴇᴛᴄ ʙᴜᴛ ɪ ᴍᴀɪɴʟʏ ʜᴀᴠᴇ ᴛʜᴇ ᴀᴅᴠᴀɴᴄᴇᴅ ᴀɴᴅ ʜᴀɴᴅʏ ᴀɴᴛɪꜱᴘᴀᴍ ꜱʏꜱᴛᴇᴍ ᴀɴᴅ ᴛʜᴇ ꜱɪʙʏʟ ʙᴀɴɴɪɴɢ ꜱʏꜱᴛᴇᴍ ᴡʜɪᴄʜ ꜱᴀꜰᴇɢᴀᴜʀᴅꜱ ᴀɴᴅ ʜᴇʟᴘꜱ ʏᴏᴜʀ ɢʀᴏᴜᴘ ꜰʀᴏᴍ ꜱᴘᴀᴍᴍᴇʀꜱ."
            f"\n\n🙋🏻 ᴡʜᴀᴛ ᴄᴀɴ ɪ ᴅᴏ :"
            f"\n\n➲  ɪ ᴄᴀɴ ʀᴇꜱᴛʀɪᴄᴛ ᴜꜱᴇʀꜱ."
            f"\n\n➲  ɪ ᴄᴀɴ ᴘʟᴀʏ ʜɪɢʜ ǫᴜᴀʟɪᴛʏ ᴍᴜꜱɪᴄ ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴘꜱ ᴠᴏɪᴄᴇ ᴄʜᴀᴛ."
            f"\n\n➲  ɪ ᴄᴀɴ ɢʀᴇᴇᴛ ᴜꜱᴇʀꜱ ᴡɪᴛʜ ᴄᴜꜱᴛᴏᴍɪᴢᴀʙʟᴇ ᴡᴇʟᴄᴏᴍᴇ ᴍᴇꜱꜱᴀɢᴇꜱ ᴀɴᴅ ᴇᴠᴇɴ ꜱᴇᴛ ᴀ ɢʀᴏᴜᴘ'ꜱ ʀᴜʟᴇꜱ."
            f"\n\n➲  ɪ ᴄᴀɴ ᴡᴀʀɴ ᴜꜱᴇʀꜱ ᴜɴᴛɪʟ ᴛʜᴇʏ ʀᴇᴀᴄʜ ᴍᴀx ᴡᴀʀɴꜱ, ᴡɪᴛʜ ᴇᴀᴄʜ ᴘʀᴇᴅᴇꜰɪɴᴇᴅ ᴀᴄᴛɪᴏɴꜱ ꜱᴜᴄʜ ᴀꜱ ʙᴀɴ, ᴍᴜᴛᴇ, ᴋɪᴄᴋ, ᴇᴛᴄ."
            f"\n\n➲  ɪ ʜᴀᴠᴇ ᴀɴ ᴀᴅᴠᴀɴᴄᴇᴅ ᴀɴᴛɪ-ꜰʟᴏᴏᴅ ꜱʏꜱᴛᴇᴍ."
            f"\n\n➲  ɪ ʜᴀᴠᴇ ᴀ ɴᴏᴛᴇ ᴋᴇᴇᴘɪɴɢ ꜱʏꜱᴛᴇᴍ, ʙʟᴀᴄᴋʟɪꜱᴛꜱ, ᴀɴᴅ ᴇᴠᴇɴ ᴘʀᴇᴅᴇᴛᴇʀᴍɪɴᴇᴅ ʀᴇᴘʟɪᴇꜱ ᴏɴ ᴄᴇʀᴛᴀɪɴ ᴋᴇʏᴡᴏʀᴅꜱ."
            f"\n\n➲  ɪ ᴄʜᴇᴄᴋ ꜰᴏʀ ᴀᴅᴍɪɴꜱ ᴘᴇʀᴍɪꜱꜱɪᴏɴꜱ ʙᴇꜰᴏʀᴇ ᴇxᴇᴄᴜᴛɪɴɢ ᴀɴʏ ᴄᴏᴍᴍᴀɴᴅ ᴀɴᴅ ᴍᴏʀᴇ ꜱᴛᴜꜰꜰꜱ."
            f"\n\n\n *ɪꜰ ʏᴏᴜ ʜᴀᴠᴇ ᴀɴʏ ǫᴜᴇꜱᴛɪᴏɴ ᴀʙᴏᴜᴛ ᴄʀᴇᴀᴛᴏʀ ᴘᴀᴠᴀɴ ʙᴏᴛ ᴛʜᴇɴ ᴄᴏɴᴛᴀᴄᴛ ᴜꜱ ᴀᴛ ꜱᴜᴘᴘᴏʀᴛ ᴄʜᴀᴛ ᴀɴᴅ ᴛᴏ ᴋᴇᴇᴘ ʏᴏᴜʀꜱᴇʟꜰ ᴜᴘᴅᴀᴛᴇᴅ ᴀʙᴏᴜᴛ ᴄʀᴇᴀᴛᴏʀ ᴘᴀᴠᴀɴ ᴊᴏɪɴ* [ᴛʜᴇ ᴄʀᴇᴀᴛᴏʀ ᴘᴀᴠᴀɴ](https://t.me/TheCreatorPavan).",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text="ᴀᴅᴍɪɴs ꜱᴛɪɴɢ", callback_data="aboutmanu_permis"
                        ),
                        InlineKeyboardButton(
                            text="ᴀɴᴛɪ ꜱᴘᴀᴍ", callback_data="aboutmanu_spamprot"
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            text="ᴄʀᴇᴅɪᴛꜱ", callback_data="aboutmanu_credit"
                        ),
                        InlineKeyboardButton(
                            text="ᴛ.ᴀ.ᴄ", callback_data="aboutmanu_tac"
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            text="ʜᴏᴡ ᴛᴏ ᴜꜱᴇ", callback_data="aboutmanu_howto"
                        )
                    ],
                    [InlineKeyboardButton(text="🔙 ʜᴏᴍᴇ ʙᴀᴄᴋ", callback_data="aboutmanu_back")],
                ]
            ),
        )
    elif query.data == "aboutmanu_back":
        query.message.edit_text(
            PM_START_TEXT.format(
                escape_markdown(context.bot.first_name),
                escape_markdown(get_readable_time((time.time() - StartTime))),
                sql.num_users(),
                sql.num_chats(),
            ),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.MARKDOWN,
            timeout=60,
        )

    elif query.data == "aboutmanu_howto":
        query.message.edit_text(
            text=f"* ｢ BASIC HELP 」*"
            f"\n\n*ʜᴇʀᴇ ɪꜱ ᴀ ꜱᴏᴍᴇ ʙᴀꜱɪᴄ ʜᴇʟᴘ ᴄᴏᴍᴍᴀɴᴅꜱ ᴏꜰ ᴄʀᴇᴀᴛᴏʀ ᴘᴀᴠᴀɴ ʀᴏʙᴏᴛ. ᴜꜱᴇ ᴛʜᴇ ꜰᴏʟʟᴏᴡɪɴɢ ʙᴜᴛᴛᴏɴꜱ ꜰᴏʀ ᴋɴᴏᴡɪɴɢ ᴍᴏʀᴇ ɪɴꜰᴏ ᴀɴᴅ ꜰᴏʀ ᴍᴏʀᴇ ꜱᴇᴇ ᴍᴀɪɴ ᴄᴏᴍᴍᴀɴᴅ ꜱᴇᴄᴛɪᴏɴ.* \n"
            f"\n\n*© @TheCreatorPavan*\n"
            f"",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text="ᴀᴅᴍɪɴs ꜱᴛɪɴɢ", callback_data="aboutmanu_permis"
                        ),
                        InlineKeyboardButton(
                            text="ᴀɴᴛɪ ꜱᴘᴀᴍ", callback_data="aboutmanu_spamprot"
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            text="ᴍᴜꜱɪᴄ ꜱᴇᴛᴜᴘ", callback_data="aboutmanu_cbguide"
                        ),
                    ],
                    [InlineKeyboardButton(text="🔙 ʜᴏᴍᴇ ʙᴀᴄᴋ", callback_data="aboutmanu_")],
                ]
            ),
        )
    elif query.data == "aboutmanu_credit":
        query.message.edit_text(
            text=f"*｢ About Credit 」*\n\n*◈  ᴄʀᴇᴀᴛᴏʀ ᴘᴀᴠᴀɴ ɪꜱ ᴛʜᴇ ʀᴇᴅɪꜱɪɢɴᴇᴅ ᴠᴇʀꜱɪᴏɴ ᴏꜰ ᴅᴀɪꜱʏ ᴀɴᴅ ꜱᴀɪᴛᴀᴍᴀ ᴀɴᴅ ᴏᴛʜʀᴇʀ ꜰᴏʀ ᴛʜᴇ ʙᴇꜱᴛ ᴘᴇʀꜰᴏʀᴍᴀɴᴄᴇ.*"
            f"\n\n*◈  ꜰʀᴏᴍ ᴏᴜʀ ᴀʙɪʟɪᴛʏ ᴡᴇ ᴛʀʏ ᴛᴏ ᴍᴀᴋᴇ ɪᴛ ᴇᴀꜱɪᴇʀ ᴀɴᴅ ꜰᴀꜱᴛᴇʀ.*"
            f"\n\n*◈  ꜱᴘᴇᴄɪᴀʟ ᴛʜᴀɴᴋꜱ ᴛᴏ -----.*"
            f"\n\n*◈  ᴄʀᴇᴅɪᴛ ᴏꜰ ʀᴇᴅᴇꜱɪɢɴɪɴɢ ᴛᴏ ᴘᴀᴠᴀɴ ᴀɴᴅ ᴀᴀʏᴜꜱʜ.*"
            f"\n\n*◈  ꜱᴏᴍᴇ ᴍᴏᴅᴜʟᴇꜱ ɪɴ ᴛʜɪꜱ ʙᴏᴛ ɪꜱ ᴏᴡɴᴇᴅ ʙʏ ᴅɪꜰꜰᴇʀᴇɴᴛ ᴀᴜᴛʜᴏʀꜱ, ꜱᴏ, ᴀʟʟ ᴄʀᴇᴅɪᴛꜱ ɢᴏᴇꜱ ᴛᴏ ᴛʜᴇᴍ ᴀʟꜱᴏ ꜰᴏʀ ᴘᴀᴜʟ ʟᴀʀꜱᴏɴ ꜰᴏʀ ᴍᴀʀɪᴇ.*"
            f"\n\n*◈  ɪꜰ ᴀɴʏ ǫᴜᴇsᴛɪᴏɴ ᴀʙᴏᴜᴛ ᴄʀᴇᴀᴛᴏʀ ᴘᴀᴠᴀɴ ʙᴏᴛ, ʟᴇᴛ ᴜꜱ ᴋɴᴏᴡ ᴀᴛ ᴏᴜʀ ꜱᴜᴘᴘᴏʀᴛ ᴄʜᴀᴛ ɢʀᴏᴜᴘ.*",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(
                [
                   [
                      InlineKeyboardButton(text="Pᴀᴠᴀɴ", url="http://t.me/PavanxD"),
                      InlineKeyboardButton(text="Aʏᴜꜱʜ", url="http://t.me/op_aayush"),
                   ],[
                      InlineKeyboardButton(text="ꜱᴜᴘᴘᴏʀᴛ ᴄʜᴀᴛ", url="http://t.me/CreatorPavanSupport"),
                   ],
        [InlineKeyboardButton(text="🔙 ʜᴏᴍᴇ ʙᴀᴄᴋ", callback_data="aboutmanu_")]]
            ),
        )

    elif query.data == "aboutmanu_permis":
        query.message.edit_text(
            text=f"<b> ｢ Admin Permissions 」</b>"
            f"\n\nᴛᴏ ᴀᴠᴏɪᴅ ꜱʟᴏᴡɪɴɢ ᴅᴏᴡɴ, ᴄʀᴇᴀᴛᴏʀ ᴘᴀᴠᴀɴ ʀᴏʙᴏᴛꜱ ᴄᴀᴄʜᴇꜱ ᴀᴅᴍɪɴ ʀɪɢʜᴛꜱ ꜰᴏʀ ᴇᴀᴄʜ ᴜꜱᴇʀ. ᴛʜɪꜱ ᴄᴀᴄʜᴇ ʟᴀꜱᴛꜱ ᴀʙᴏᴜᴛ 10 ᴍɪɴᴜᴛᴇꜱ ;  ᴛʜɪꜱ ᴍᴀʏ ᴄʜᴀɴɢᴇ ɪɴ ᴛʜᴇ ꜰᴜᴛᴜʀᴇ. ᴛʜɪꜱ ᴍᴇᴀɴꜱ ᴛʜᴀᴛ ɪꜰ ʏᴏᴜ ᴘʀᴏᴍᴏᴛᴇ ᴀ ᴜꜱᴇʀ ᴍᴀɴᴜᴀʟʟʏ (ᴡɪᴛʜᴏᴜᴛ ᴜꜱɪɴɢ ᴛʜᴇ /ᴘʀᴏᴍᴏᴛᴇ ᴄᴏᴍᴍᴀɴᴅ), ᴄʀᴇᴀᴛᴏʀ ᴘᴀᴠᴀɴ ʀᴏʙᴏᴛ ᴡɪʟʟ ᴏɴʟʏ ꜰɪɴᴅ ᴏᴜᴛ ~10 ᴍɪɴᴜᴛᴇꜱ ʟᴀᴛᴇʀ.\n\nɪꜰ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴜᴘᴅᴀᴛᴇ ᴛʜᴇᴍ ɪᴍᴍᴇᴅɪᴀᴛᴇʟʏ, ʏᴏᴜ ᴄᴀɴ ᴜꜱᴇ ᴛʜᴇ /ᴀᴅᴍɪɴᴄᴀᴄʜᴇ ᴄᴏᴍᴍᴀɴᴅ, ᴛʜᴛᴀ'ʟʟ ꜰᴏʀᴄᴇ ᴄʀᴇᴀᴛᴏʀ ᴘᴀᴠᴀɴ ʀᴏʙᴏᴛ ᴛᴏ ᴄʜᴇᴄᴋ ᴡʜᴏ ᴛʜᴇ ᴀᴅᴍɪɴꜱ ᴀʀᴇ ᴀɢᴀɪɴ ᴀɴᴅ ᴛʜᴇɪʀ ᴘᴇʀᴍɪꜱꜱɪᴏɴꜱ\n\nɪꜰ ʏᴏᴜ ᴀʀᴇ ɢᴇᴛᴛɪɴɢ ᴀ ᴍᴇꜱꜱᴀɢᴇ ꜱᴀʏɪɴɢ :  `ʏᴏᴜ ᴍᴜꜱᴛ ʙᴇ ᴛʜɪꜱ ᴄʜᴀᴛ ᴀᴅᴍɪɴɪꜱᴛʀᴀᴛᴏʀ ᴛᴏ ᴘᴇʀꜰᴏʀᴍ ᴛʜɪꜱ ᴀᴄᴛɪᴏɴ !`\n\nᴛʜɪꜱ ʜᴀꜱ ɴᴏᴛʜɪɴɢ ᴛᴏ ᴅᴏ ᴡɪᴛʜ ᴄʀᴇᴀᴛᴏʀ ᴘᴀᴠᴀɴ ʀᴏʙᴏᴛ'ꜱ ʀɪɢʜᴛꜱ ; ᴛʜɪꜱ ɪꜱ ᴀʟʟ ᴀʙᴏᴜᴛ ʏᴏᴜʀ ᴘᴇʀᴍɪꜱꜱɪᴏɴꜱ ᴀꜱ ᴀɴ ᴀᴅᴍɪɴ. ᴄʀᴇᴀᴛᴏʀ ᴘᴀᴠᴀɴ ʀᴏʙᴏᴛ ʀᴇꜱᴘᴇᴄᴛꜱ ᴀᴅᴍɪɴ ᴘᴇʀᴍɪꜱꜱɪᴏɴꜱ ; ɪꜰ ʏᴏᴜ ᴅᴏ ɴᴏᴛ ʜᴀᴠᴇ ᴛʜᴇ ʙᴀɴ ᴜꜱᴇʀꜱ ᴘᴇʀᴍɪꜱꜱɪᴏɴ ᴀꜱ ᴀ ᴛᴇʟᴇɢʀᴀᴍ ᴀᴅᴍɪɴ, ʏᴏᴜ ᴡᴏɴ'ᴛ ʙᴇ ᴀʙʟᴇ ᴛᴏ ʙᴀɴ ᴜꜱᴇʀꜱ ᴡɪᴛʜ ᴄʀᴇᴀᴛᴏʀ ᴘᴀᴠᴀɴ ʀᴏʙᴏᴛ. ꜱɪᴍɪʟᴀʀʟʏ, ᴛᴏ ᴄʜᴀɴɢᴇ ᴄʀᴇᴀᴛᴏʀ ᴘᴀᴠᴀɴ ʀᴏʙᴏᴛ ꜱᴇᴛᴛɪɴɢꜱ, ʏᴏᴜ ɴᴇᴇᴅ ᴛᴏ ʜᴀᴠᴇ ᴛʜᴇ ᴄʜᴀɴɢᴇ ɢʀᴏᴜᴘ ɪɴꜰᴏ ᴘᴇʀᴍɪꜱꜱɪᴏɴ.\n\n*ᴛʜᴇ ᴍᴇꜱꜱᴀɢᴇ ᴠᴇʀʏ ᴄʟᴇᴀʀʟʏ ꜱᴀʏꜱ ᴛʜᴀᴛ ʏᴏᴜ ɴᴇᴇᴅ ᴛʜᴇꜱᴇ ʀɪɢʜᴛꜱ - ɴᴏᴛ ᴄʀᴇᴀᴛᴏʀ ᴘᴀᴠᴀɴ ʀᴏʙᴏᴛ*",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(text="🔙 ʜᴏᴍᴇ ʙᴀᴄᴋ", callback_data="aboutmanu_")]]
            ),
        )
    
    
    elif query.data == "aboutmanu_spamprot":
        query.message.edit_text(
            text="* ｢ Anti-Spam Settings 」*"
            "\n- /antispam <on/off/yes/no>: Change antispam security settings in the group, or return your current settings(when no arguments)."
            "\n_This helps protect you and your groups by removing spam flooders as quickly as possible._"
            "\n\n- /setflood <int/'no'/'off'>: enables or disables flood control"
            "\n- /setfloodmode <ban/kick/mute/tban/tmute> <value>: Action to perform when user have exceeded flood limit. ban/kick/mute/tmute/tban"
            "\n_Antiflood allows you to take action on users that send more than x messages in a row. Exceeding the set flood will result in restricting that user._"
            "\n\n- /addblacklist <triggers>: Add a trigger to the blacklist. Each line is considered one trigger, so using different lines will allow you to add multiple triggers."
            "\n- /blacklistmode <off/del/warn/ban/kick/mute/tban/tmute>: Action to perform when someone sends blacklisted words."
            "\n_Blacklists are used to stop certain triggers from being said in a group. Any time the trigger is mentioned, the message will immediately be deleted. A good combo is sometimes to pair this up with warn filters!_"
            "\n\n- /reports <on/off>: Change report setting, or view current status."
            "\n • If done in pm, toggles your status."
            "\n • If in chat, toggles that chat's status."
            "\n_If someone in your group thinks someone needs reporting, they now have an easy way to call all admins._"
            "\n\n- /lock <type>: Lock items of a certain type (not available in private)"
            "\n- /locktypes: Lists all possible locktypes"
            "\n_The locks module allows you to lock away some common items in the telegram world; the bot will automatically delete them!_"
            '\n\n- /addwarn <keyword> <reply message>: Sets a warning filter on a certain keyword. If you want your keyword to be a sentence, encompass it with quotes, as such: /addwarn "very angry" This is an angry user. '
            "\n- /warn <userhandle>: Warns a user. After 3 warns, the user will be banned from the group. Can also be used as a reply."
            "\n- /strongwarn <on/yes/off/no>: If set to on, exceeding the warn limit will result in a ban. Else, will just kick."
            "\n_If you're looking for a way to automatically warn users when they say certain things, use the /addwarn command._"
            "\n\n- /welcomemute <off/soft/strong>: All users that join, get muted"
            "\n_ A button gets added to the welcome message for them to unmute themselves. This proves they aren't a bot! soft - restricts users ability to post media for 24 hours. strong - mutes on join until they prove they're not bots._",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(text="Back", callback_data="aboutmanu_")]]
            ),
        )
    elif query.data == "aboutmanu_tac":
        query.message.edit_text(
            text=f"<b> ｢ Terms and Conditions 」</b>\n"
            f"\n<i>To Use This Bot, You Need To Read Terms and Conditions Carefully.</i>\n"
            f"\n✪ We always respect your privacy. We never log into bot's api and spying on you. We use a encripted database. Bot will automatically stops if someone logged in with api."
            f"\n✪ This hardwork is done by @CreatorPavanNetwork spending many sleepless nights.. So, Respect it."
            f"\n✪ Some modules in this bot is owned by different authors, So, All credits goes to them Also for <b>Paul Larson for Marie</b>."
            f"\n✪ If you need to ask anything about this bot, Go @CreatorPavanSupport."
            f"\n✪ If you asking nonsense in Support Chat, you will get warned/banned."
            f"\n✪ All api's we used owned by originnal authors. Some api's we use Free version. Please don't overuse AI Chat."
            f"\n\nFor any kind of help, related to this bot, Join @CreatorPavanSupport."
            f"\n\n<i>Terms & Conditions will be changed anytime</i>\n",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        
                        InlineKeyboardButton(text="🔙 ʜᴏᴍᴇ ʙᴀᴄᴋ", callback_data="aboutmanu_"),
                    ]
                ]
            ),
        )
    elif query.data == "aboutmanu_cbguide":
        query.message.edit_text(
            text=f"* ｢ How To Setup Music 」*\n"
            f"\n\n*◈  ꜰɪʀꜱᴛ ᴀᴅᴅ ᴍᴇ ᴛᴏ ᴜʀ ɢʀᴏᴜᴘ.*"
            f"\n\n*◈  ᴛʜᴇɴ ᴘʀᴏᴍᴏᴛᴇ ᴍᴇ ᴀꜱ ᴀᴅᴍɪɴ ᴀɴᴅ ɢɪᴠᴇ ᴀʟʟ ᴘᴇʀᴍɪꜱꜱɪᴏɴꜱ ᴇxᴄᴇᴘᴛ ᴀɴᴏɴʏᴍᴏᴜꜱ ᴀᴅᴍɪɴ.*"
            f"\n\n*◈  ᴀꜰᴛᴇʀ ᴘʀᴏᴍᴏᴛᴇ ᴍᴇ ꜱᴛᴀʀᴛ ᴠᴏɪᴄᴇ ᴄʜᴀᴛ ᴏꜰ ᴜʀ ɢʀᴏᴜᴘ ʙᴇꜰᴏʀᴇ ᴛʜᴀᴛ ꜱᴇɴᴅ* `/reload` *ᴄᴏᴍᴍᴀɴᴅ ɪɴ ᴜʀ ᴄʜᴀᴛ ɢʀᴏᴜᴘ.*"
            f"\n\n*◈  ᴛʜᴇɴ ꜱᴇɴᴅ ᴘʟᴀʏ ᴄᴏᴍᴍᴀɴᴅ ᴀɴᴅ ᴜʀ ꜱᴏɴɢ ɴᴀᴍᴇ.*"
            f"\n\n*◈  ᴍᴀᴋᴇ ꜱᴜʀᴇ ᴜ ꜱᴛᴀʀᴛᴇᴅ ᴠᴏɪᴄᴇ ᴄʜᴀᴛ ʙᴇꜰᴏʀᴇ ᴛʜᴀᴛ*"
            f"\n\n*◈  ɪꜰ ᴀɴʏ ᴛʏᴘᴇ ᴏꜰ ᴇʀʀᴏʀ ᴡɪʟʟ ʙᴇ ᴄᴏᴍᴇꜱ ᴛʜᴇɴ ᴜ ᴄᴀɴ ᴄᴏɴᴛᴀᴄᴛ ᴜꜱ ᴀᴛ ᴏᴜʀ ꜱᴜᴘᴘᴏʀᴛ ᴄʜᴀᴛ ɢʀᴏᴜᴘ.*\n"
            f"\n\n*© @TheCreatorPavan*\n",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        
                        InlineKeyboardButton(
                            text="ᴍᴜꜱɪᴄ ᴄᴏᴍᴍᴀɴᴅꜱ ʟɪꜱᴛ", callback_data="aboutmanu_cbhelps"
                        ),
                    ],
                    [ 
                      InlineKeyboardButton(text="🔙 ʜᴏᴍᴇ ʙᴀᴄᴋ", callback_data="aboutmanu_back"),
                    ],
                ]
            ),
        )
    elif query.data == "aboutmanu_cbhelps":
        query.message.edit_text(
            text=f"* ｢ Music Command 」*\n"
            f"\n\n1️⃣ »*/play  :  ꜰᴏʀ ᴘʟᴀʏɪɴɢ ᴜʀ ꜱᴏɴɢ.*"
            f"\n\n2️⃣ »*/pause  :  ꜰᴏʀ ᴘᴀᴜꜱᴇᴅ ꜱᴛʀᴇᴀᴍɪɴɢ.*"
            f"\n\n3️⃣ »*/resume  :  ꜰᴏʀ ʀᴇꜱᴜᴍᴇ ꜱᴛʀᴇᴀᴍɪɴɢ.*"
            f"\n\n4️⃣ »*/end  :  ꜰᴏʀ ᴇɴᴅ ꜱᴛʀᴇᴀᴍɪɴɢ.*"
            f"\n\n5️⃣ »*/song  :  ꜰᴏʀ ᴅᴏᴡɴʟᴏᴀᴅ ꜱᴏɴɢ.*"
            f"\n\n6️⃣ »*/video  :  ꜰᴏʀ ᴅᴏᴡɴʟᴏᴀᴅ ᴠɪᴅᴇᴏ.*"
            f"\n\n7️⃣ »*/search  :  ꜱᴇᴀʀᴄʜɪɴɢ ꜰʀᴏᴍ ʏᴏᴜᴛᴜʙᴇ.*"
            f"\n\n8️⃣ »*/userbotjoin  :  ꜰᴏʀ ᴊᴏɪɴɪɴɢ ᴀꜱꜱɪꜱᴛᴀɴᴛ.*"
            f"\n\n9️⃣ »*/userbotleave  :  ꜰᴏʀ ʟᴇᴀᴠᴇꜱ ᴀꜱꜱɪꜱᴛᴀɴᴛ.*"
            f"\n\n\n*© @TheCreatorPavan*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text="ʜᴏᴡ ᴛᴏ ᴜꜱᴇ", callback_data="aboutmanu_cbguide"
                        ),
                        
                    ],
                   [
                       InlineKeyboardButton(text="🔙 ʜᴏᴍᴇ ʙᴀᴄᴋ", callback_data="aboutmanu_back"),
                   ],
                ]
            ),
        )



@run_async
@spamcheck
def get_help(update, context):
    chat = update.effective_chat  # type: Optional[Chat]
    args = update.effective_message.text.split(None, 1)

    # ONLY send help in PM
    if chat.type != chat.PRIVATE:

        # update.effective_message.reply_text("Contact me in PM to get the list of possible commands.",
        update.effective_message.reply_text(tl(update.effective_message, "Hubungi saya di PM untuk mendapatkan daftar perintah."),
                                            reply_markup=InlineKeyboardMarkup(
                                                [[InlineKeyboardButton(text=tl(update.effective_message, "Tolong"),
                                                                       url="t.me/{}?start=help".format(
                                                                           context.bot.username))]]))
        return

    elif len(args) >= 2 and any(args[1].lower() == x for x in HELPABLE):
        module = args[1].lower()
        text = tl(update.effective_message, "Ini adalah bantuan yang tersedia untuk modul *{}*:\n").format(HELPABLE[module].__mod_name__) \
               + tl(update.effective_message, HELPABLE[module].__help__)
        send_help(chat.id, text, InlineKeyboardMarkup([[InlineKeyboardButton(text=tl(update.effective_message, "⬅️ Kembali"), callback_data="help_back")]]))

    else:
        send_help(chat.id, tl(update.effective_message, HELP_STRINGS))


def send_settings(chat_id, user_id, user=False):
    if user:
        if USER_SETTINGS:
            settings = "\n\n".join(
                "*{}*:\n{}".format(mod.__mod_name__, mod.__user_settings__(user_id)) for mod in USER_SETTINGS.values())
            dispatcher.bot.send_message(user_id, tl(chat_id, "These are your current settings:") + "\n\n" + settings,
                                        parse_mode=ParseMode.MARKDOWN)

        else:
            dispatcher.bot.send_message(user_id, tl(chat_id, "Sepertinya tidak ada pengaturan khusus pengguna yang tersedia 😢"),
                                        parse_mode=ParseMode.MARKDOWN)

    else:
        if CHAT_SETTINGS:
            chat_name = dispatcher.bot.getChat(chat_id).title
            dispatcher.bot.send_message(user_id,
                                        text=tl(chat_id, "Modul mana yang ingin Anda periksa untuk pengaturan {}?").format(
                                            chat_name),
                                        reply_markup=InlineKeyboardMarkup(
                                            paginate_modules(0, CHAT_SETTINGS, "stngs", chat=chat_id)))
        else:
            dispatcher.bot.send_message(user_id, tl(chat_id, "Sepertinya tidak ada pengaturan obrolan yang tersedia 😢\nKirim ini "
                                                 "ke obrolan Anda sebagai admin untuk menemukan pengaturannya saat ini!"),
                                        parse_mode=ParseMode.MARKDOWN)


@run_async
def settings_button(update, context):
    query = update.callback_query
    user = update.effective_user
    mod_match = re.match(r"stngs_module\((.+?),(.+?)\)", query.data)
    prev_match = re.match(r"stngs_prev\((.+?),(.+?)\)", query.data)
    next_match = re.match(r"stngs_next\((.+?),(.+?)\)", query.data)
    back_match = re.match(r"stngs_back\((.+?)\)", query.data)
    try:
        if mod_match:
            chat_id = mod_match.group(1)
            module = mod_match.group(2)
            chat = context.bot.get_chat(chat_id)
            getstatusadmin = context.bot.get_chat_member(chat_id, user.id)
            isadmin = getstatusadmin.status in ('administrator', 'creator')
            if isadmin == False or user.id != OWNER_ID:
                query.message.edit_text("Your admin status has changed")
                return
            text = tl(update.effective_message, "*{}* memiliki pengaturan berikut untuk modul *{}* module:\n\n").format(escape_markdown(chat.title),
                                                                                     CHAT_SETTINGS[
                                                                                        module].__mod_name__) + \
                   CHAT_SETTINGS[module].__chat_settings__(chat_id, user.id)
            try:
                set_button = CHAT_SETTINGS[module].__chat_settings_btn__(chat_id, user.id)
            except AttributeError:
                set_button = []
            set_button.append([InlineKeyboardButton(text=tl(query.message, "⬅️ kembali"),
                                                               callback_data="stngs_back({})".format(chat_id))])
            query.message.edit_text(text=text,
                                  parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=InlineKeyboardMarkup(set_button))

        elif prev_match:
            chat_id = prev_match.group(1)
            curr_page = int(prev_match.group(2))
            chat = context.bot.get_chat(chat_id)
            query.message.reply_text(text=tl(update.effective_message, "Hai! Ada beberapa pengaturan untuk {} - lanjutkan dan pilih "
                                       "apa yang Anda minati.").format(chat.title),
                                  reply_markup=InlineKeyboardMarkup(
                                        paginate_modules(curr_page - 1, CHAT_SETTINGS, "stngs",
                                                         chat=chat_id)))

        elif next_match:
            chat_id = next_match.group(1)
            next_page = int(next_match.group(2))
            chat = context.bot.get_chat(chat_id)
            query.message.reply_text(text=tl(update.effective_message, "Hai! Ada beberapa pengaturan untuk {} - lanjutkan dan pilih "
                                       "apa yang Anda minati.").format(chat.title),
                                  reply_markup=InlineKeyboardMarkup(
                                        paginate_modules(next_page + 1, CHAT_SETTINGS, "stngs",
                                                         chat=chat_id)))

        elif back_match:
            chat_id = back_match.group(1)
            chat = context.bot.get_chat(chat_id)
            query.message.reply_text(text=tl(update.effective_message, "Hai! Ada beberapa pengaturan untuk {} - lanjutkan dan pilih "
                                       "apa yang Anda minati.").format(escape_markdown(chat.title)),
                                  parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=InlineKeyboardMarkup(paginate_modules(0, CHAT_SETTINGS, "stngs",
                                                                                     chat=chat_id)))

        # ensure no spinny white circle

        context.bot.answer_callback_query(query.id)
    except Exception as excp:
        if excp.message == "Message is not modified":
            pass
        elif excp.message == "Query_id_invalid":
            pass
        elif excp.message == "Message can't be deleted":
            pass
        else:
            query.message.edit_text(excp.message)
            LOGGER.exception("Exception in settings buttons. %s", str(query.data))


@run_async
@spamcheck
def get_settings(update, context):
    chat = update.effective_chat  # type: Optional[Chat]
    user = update.effective_user  # type: Optional[User]
    msg = update.effective_message  # type: Optional[Message]
    args = msg.text.split(None, 1)

    # ONLY send settings in PM
    if chat.type != chat.PRIVATE:
        if is_user_admin(chat, user.id):
            text = tl(update.effective_message, "Klik di sini untuk mendapatkan pengaturan obrolan ini, serta milik Anda.")
            msg.reply_text(text,
                           reply_markup=InlineKeyboardMarkup(
                               [[InlineKeyboardButton(text="Pengaturan",
                                                      url="t.me/{}?start=stngs_{}".format(
                                                          context.bot.username, chat.id))]]))
        # else:
        #     text = tl(update.effective_message, "Klik di sini untuk memeriksa pengaturan Anda.")

    else:
        send_settings(chat.id, user.id, True)


@run_async
@spamcheck
def source(update, context):
    user = update.effective_message.from_user
    chat = update.effective_chat  # type: Optional[Chat]

    if chat.type == "private":
        update.effective_message.reply_text(SOURCE_STRING, parse_mode=ParseMode.MARKDOWN)

    else:
        try:
            context.bot.send_message(user.id, SOURCE_STRING, parse_mode=ParseMode.MARKDOWN)

            update.effective_message.reply_text("You'll find in PM more info about my sourcecode.")
        except Unauthorized:
            update.effective_message.reply_text("Contact me in PM first to get source information.")




# Avoid memory dead
def memory_limit(percentage: float):
    if platform.system() != "Linux":
        print('Only works on linux!')
        return
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_AS, (int(get_memory() * 1024 * percentage), hard))

def get_memory():
    with open('/proc/meminfo', 'r') as mem:
        free_memory = 0
        for i in mem:
            sline = i.split()
            if str(sline[0]) in ('MemFree:', 'Buffers:', 'Cached:'):
                free_memory += int(sline[1])
    return free_memory

def memory(percentage=0.5):
    def decorator(function):
        def wrapper(*args, **kwargs):
            memory_limit(percentage)
            try:
                function(*args, **kwargs)
            except MemoryError:
                mem = get_memory() / 1024 /1024
                print('Remain: %.2f GB' % mem)
                sys.stderr.write('\n\nERROR: Memory Exception\n')
                sys.exit(1)
        return wrapper
    return decorator


@memory(percentage=0.8)
def main():
    test_handler = CommandHandler("test", test)
    start_handler = CommandHandler("start", start, pass_args=True)

    help_handler = CommandHandler("help", get_help)
    help_callback_handler = CallbackQueryHandler(help_button, pattern=r"help_")

    settings_handler = CommandHandler("settings", get_settings)
    settings_callback_handler = CallbackQueryHandler(settings_button, pattern=r"stngs_")

    source_handler = CommandHandler("source", source)
    M_CONNECT_BTN_HANDLER = CallbackQueryHandler(m_connect_button, pattern=r"main_connect")
    M_SETLANG_BTN_HANDLER = CallbackQueryHandler(m_change_langs, pattern=r"main_setlang")

    # dispatcher.add_handler(test_handler)
    dispatcher.add_handler(start_handler)
    dispatcher.add_handler(help_handler)
    dispatcher.add_handler(settings_handler)
    dispatcher.add_handler(help_callback_handler)
    dispatcher.add_handler(settings_callback_handler)
    dispatcher.add_handler(source_handler)
    dispatcher.add_handler(M_CONNECT_BTN_HANDLER)
    dispatcher.add_handler(M_SETLANG_BTN_HANDLER)

    # dispatcher.add_error_handler(error_callback)

    if WEBHOOK:
        LOGGER.info("Pengguna webhooks")
        updater.start_webhook(listen="127.0.0.1",
                              port=PORT,
                              url_path=TOKEN)

        if CERT_PATH:
            updater.bot.set_webhook(url=URL + TOKEN,
                                    certificate=open(CERT_PATH, 'rb'))
        else:
            updater.bot.set_webhook(url=URL + TOKEN)

    else:
        LOGGER.info("Bot Manager Anda Telah Aktif!")
        # updater.start_polling(timeout=15, read_latency=4)
        updater.start_polling(poll_interval=0.0,
                              timeout=10,
                              clean=True,
                              bootstrap_retries=-1,
                              read_latency=3.0)

    updater.idle()

if __name__ == '__main__':
    LOGGER.info("Successfully loaded modules: " + str(ALL_MODULES))
    main()
