import logging
import random
import re
import time
import os
from collections import defaultdict
from telegram import Update, ChatPermissions, MessageEntity
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext, ChatMemberHandler

# ================== الإعدادات ==================
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GROUP_ID = int(os.environ.get("ALLOWED_CHAT_ID", "0"))

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# تخزين البيانات المؤقتة
user_messages = defaultdict(list)
user_activity = defaultdict(list)
user_info_cache = {}
user_link_warnings = defaultdict(int)
user_spam_data = defaultdict(lambda: {"last_content": None, "count": 0, "warnings": 0})
is_chat_locked = False

# قائمة الكلمات المسيئة
OFFENSIVE_WORDS = [
    "عير", "عيري", "زب", "زبي", "كس", "كسي", "كسكوس", "طيز", "طيزي", "طيزج", "كسج", "كسك", 
    "انيج", "انيك", "نيجه", "منيوج", "منيوجه", "نجت", "اتنايج", "نتنايج", "انيجج", "انيجها", 
    "صدرج", "ديوس", "ديسج", "ديوسج", "اجب", "جبيت", "ناجج", "نيجتي", "انبعصت", "بعصك", 
    "بعصتي", "مبعبص", "مبعوص", "ابعصه", "احطه بيج", "احطه بيك", "يوجعج مو", "عيوره", "عيورة"
]

# ================== الردود للكلمات المفتاحية ==================
KEYWORD_REPLIES = {
    r"(السلام|السلام عليكم)": ["وعليكم السلام ورحمة الله وبركاته 🤍", "أهلاً وسهلاً 🌸"],
    r"\bجوعان\b": ["تاكل سم 😝"],
    r"\bجوعانه\b": ["تاكلين سم 😝"],
    r"(مساء الخير|مساء)": ["مساء النور 🌙", "مساء العسل 🙊", "مساء الورد 🌸", "مساء الحلوين 🙂"],
    r"(صباح الخير|صباحو|شباحو)": ["ياهلا 😎", "صباح الورد 🌸", "صباح العسل 🤩", "شباحو 😎", "صباحو ♥️"],
    r"(قيصر|قيصر مجيد|قيقو)": ["من تكتفي من المجال مادياً لازم بعد تعوفه🙂", "ضريبة الشهره لازم تدفعها غصباً عليك😎"],
    r"قطوزه": ["قلب قطوزه♥️", "ها عيني🙊", "شتريد!", "شتريد من صخام😒", "هرمونات لاتحاجيني🤧", "عيون قطوزه🤩"],
    r"(بوت|بوته|بتبوته|بتبوت|بوتي)": ["بلا مشاكل حبيبي 🙂", "عندي أسم تره 😐", "ماردنه الطلايب بس تجي كوه 😌", "حبيبي زغلول", "ها عيني", "أنجب", "شتريد !"],
    r"(احبك|أحبك|احبنك)": ["أموت عليك🙂", "بعد كلبي♥️", "واني هم", "كافي لاتصير لوكي ", "اشكد ملطلط"]
}

ORAS_RANDOM_REPLIES = ["تاج رأسي هذا", "قلبه", "عطره", "شتريد!", "نائيم", "طالع", "هسه يجي", "الله نطاه الله اخذه"]
EYES_RANDOM_REPLIES = ["ابوسهن", "تخبل", "اووف يموتن", "ماكو منها"]
ORAS_STICKER = "CAACAgIAAxkBArDcAWlxZjeYwJgn17ry9c0Qebo82BCIAAKBAAMfiWYWFMGaTmWoWNw4BA"
EYES_STICKER = "CAACAgIAAyEFAATHjkDrAALWfWllHK2VnEyxJ4rrOKVBSmta14zVAAJjQwACXippSEGysTBm4u1KOAQ"
NOT_ADMIN_REPLIES = ["هذا الامر فقط من الادمن أنت مو admin 😏", "أنت مو ادمن حبيبي 😉", "ننظر بقضيتك 🤧", "صرت أدمن ومادري 🙂", "نخابرك نخابرك فيما بعد 😆", "لا تلح 😏", "حاول مره اخره😂😝"]
KICK_REPLIES = ["طردته😁🙊", "اطلع بره😎"]

def is_admin(update: Update, context: CallbackContext):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return False
    try:
        member = context.bot.get_chat_member(chat.id, user.id)
        return member.status in ["administrator", "creator"]
    except Exception as e:
        logging.error(f"Admin check error: {e}")
        return False

def spam_filter(update: Update, context: CallbackContext):
    msg = update.message
    user = update.effective_user
    chat = update.effective_chat
    if not msg or not user or not chat or is_admin(update, context):
        return False

    # Identify content for spam detection (text, sticker_id, animation_id, etc.)
    content = None
    if msg.text:
        content = f"text:{msg.text}"
    elif msg.sticker:
        content = f"sticker:{msg.sticker.file_id}"
    elif msg.animation:
        content = f"animation:{msg.animation.file_id}"
    elif msg.photo:
        content = f"photo:{msg.photo[-1].file_id}"
    
    if not content:
        return False

    user_id = user.id
    chat_id = chat.id
    data = user_spam_data[user_id]

    if data["last_content"] == content:
        data["count"] += 1
    else:
        data["last_content"] = content
        data["count"] = 1

    if data["count"] >= 5:
        try:
            msg.delete()
            data["count"] = 0 # Reset count after hitting limit
            data["warnings"] += 1
            name = user.username or user.first_name

            if data["warnings"] >= 3:
                # Delete all recent messages from this user
                for m_id in list(user_messages.get(user_id, [])):
                    try: context.bot.delete_message(chat_id, m_id)
                    except: pass
                
                context.bot.kick_chat_member(chat_id, user_id, revoke_messages=True)
                context.bot.send_message(
                    chat_id,
                    f"🚫 تم طرد المستخدم @{name} وحذف كافة رسائله.\n📌 السبب: تكرار السبام (التكرار) بشكل مفرط رغم التحذيرات المتتالية."
                )
                user_spam_data.pop(user_id, None)
                user_messages.pop(user_id, None)
            else:
                context.bot.send_message(
                    chat_id,
                    f"⚠️ تحذير للمستخدم: @{name}\n📌 يمنع تكرار الرسائل أو الاستيكرات أكثر من 5 مرات.\nالتحذير رقم: {data['warnings']}/3"
                )
            return True
        except Exception as e:
            logging.error(f"Spam filter error: {e}")
            
    return False

def link_filter(update: Update, context: CallbackContext):
    msg = update.message
    user = update.effective_user
    chat = update.effective_chat
    if not msg or not user or not chat or is_admin(update, context):
        return False

    has_link = False
    if msg.entities:
        for entity in msg.entities:
            if entity.type in [MessageEntity.URL, MessageEntity.TEXT_LINK]:
                has_link = True
                break
    
    if not has_link and msg.caption_entities:
        for entity in msg.caption_entities:
            if entity.type in [MessageEntity.URL, MessageEntity.TEXT_LINK]:
                has_link = True
                break

    if has_link:
        user_id = user.id
        chat_id = chat.id
        user_link_warnings[user_id] += 1
        
        try:
            msg.delete()
            name = user.username or user.first_name
            
            if user_link_warnings[user_id] >= 2:
                context.bot.kick_chat_member(chat_id, user_id, revoke_messages=True)
                context.bot.send_message(
                    chat_id, 
                    f"🚫 تم طرد المستخدم @{name} وحذف رسائله.\nالسبب: تكرار إرسال الروابط رغم التحذير."
                )
                user_link_warnings.pop(user_id, None)
                user_messages.pop(user_id, None)
            else:
                context.bot.send_message(
                    chat_id,
                    f"📌 لا ترسل روابط هنا 🚫\nكررها = طرد وحذف رسائل 🚪\n\nالمستخدم: @{name}"
                )
            return True
        except Exception as e:
            logging.error(f"Link filter error: {e}")
            
    return False

def offensive_filter(update: Update, context: CallbackContext):
    msg = update.message
    user = update.effective_user
    chat = update.effective_chat
    if not msg or not msg.text or not user or not chat or is_admin(update, context):
        return False
    
    text = msg.text
    user_id = user.id
    chat_id = chat.id
    
    for word in OFFENSIVE_WORDS:
        if word in text:
            try:
                msg.delete()
                for m_id in list(user_messages.get(user_id, [])):
                    try:
                        context.bot.delete_message(chat_id, m_id)
                    except:
                        pass
                context.bot.kick_chat_member(chat_id, user_id, revoke_messages=True)
                name = user.username or user.first_name
                context.bot.send_message(chat_id, f"🚫 تم طرد المستخدم @{name} وحذف رسائله.\n📌 السبب: استخدام كلمات مسيئة وغير لائقة.")
                user_messages.pop(user_id, None)
                return True
            except Exception as e:
                logging.error(f"Offensive filter error: {e}")
    return False

def track_activity(update: Update, context: CallbackContext):
    global is_chat_locked
    if update.chat_member:
        handle_chat_member_update(update, context)
        return
    
    chat = update.effective_chat
    msg = update.message
    user = update.effective_user
    
    if not chat or chat.id != GROUP_ID or not msg or not user:
        return
        
    # Check if chat is locked for non-admins
    if is_chat_locked and not is_admin(update, context):
        try:
            msg.delete()
            return
        except:
            return

    # Check spam first (Repeated content)
    if spam_filter(update, context):
        return

    # Check links
    if link_filter(update, context):
        return

    # Check offensive words
    if offensive_filter(update, context):
        return
        
    user_id = user.id
    user_messages[user_id].append(msg.message_id)
    if len(user_messages[user_id]) > 50:
        user_messages[user_id] = user_messages[user_id][-50:]
        
    user_activity[user_id].append(time.time())
    
    # Update cache and check for name changes
    if user_id not in user_info_cache:
        user_info_cache[user_id] = {'name': user.full_name, 'username': user.username}
    else:
        old_info = user_info_cache[user_id]
        curr_info = {'name': user.full_name, 'username': user.username}
        if old_info['name'] != curr_info['name'] or old_info['username'] != curr_info['username']:
            try:
                msg.delete()
                for m_id in list(user_messages.get(user_id, [])):
                    try: context.bot.delete_message(GROUP_ID, m_id)
                    except: pass
                context.bot.kick_chat_member(GROUP_ID, user_id, revoke_messages=True)
                name = user.username or user.first_name
                context.bot.send_message(GROUP_ID, f"🚫 تم طرد وحضر المستخدم @{name} وحذف رسائله.\n📌 السبب: تغيير الاسم أو المعرف (Username) ممنوع.")
                user_messages.pop(user_id, None)
                user_info_cache.pop(user_id, None)
                return
            except Exception as e:
                logging.error(f"Name change detection error: {e}")
        user_info_cache[user_id] = curr_info

def handle_chat_member_update(update: Update, context: CallbackContext):
    cm = update.chat_member
    if not cm or cm.chat.id != GROUP_ID:
        return
    
    user = cm.from_user
    if not user:
        return
    user_id = user.id
    
    if cm.new_chat_member.status in ["administrator", "creator"]:
        return

    old_info = user_info_cache.get(user_id)
    curr_info = {'name': user.full_name, 'username': user.username}
    
    if old_info and (old_info['name'] != curr_info['name'] or old_info['username'] != curr_info['username']):
        try:
            for m_id in list(user_messages.get(user_id, [])):
                try:
                    context.bot.delete_message(GROUP_ID, m_id)
                except:
                    pass
            context.bot.kick_chat_member(GROUP_ID, user_id, revoke_messages=True)
            name = curr_info['username'] or curr_info['name']
            context.bot.send_message(GROUP_ID, f"🚫 تم طرد وحضر المستخدم @{name} وحذف رسائله.\n📌 السبب: تغيير الاسم أو المعرف (Username) ممنوع.")
            user_messages.pop(user_id, None)
            user_info_cache.pop(user_id, None)
        except Exception as e:
            logging.error(f"Chat member update kick error: {e}")
    
    user_info_cache[user_id] = curr_info

def admin_actions(update: Update, context: CallbackContext):
    global is_chat_locked
    chat = update.effective_chat
    msg = update.message
    if not chat or not msg or not msg.text:
        return
    
    if chat.id != GROUP_ID:
        return

    text = msg.text.strip()
    
    # Chat Lock/Unlock Keywords
    lock_keywords = ["اغلاق الدردشة", "اغلاق الدردشه", "غلق الدردشه", "اغلاق دردشه", "اغلاق دردشة", "غلق دردشه", "طفي الدردشه", "طفي دردشه", "طفي دردشة", "طفي الدردشة"]
    unlock_keywords = ["فتح الدردشة", "فتح الدردشه", "فتح دردشه", "فتح دردشة", "تشغيل الدردشه", "تشغيل الدردشة", "تشغيل دردشة", "تشغيل دردشه"]

    if text in lock_keywords:
        if not is_admin(update, context):
            return
        is_chat_locked = True
        context.bot.send_message(chat.id, "🔒 تم إغلاق الدردشة بنجاح.")
        return

    if text in unlock_keywords:
        if not is_admin(update, context):
            return
        is_chat_locked = False
        context.bot.send_message(chat.id, "🔓 تم فتح الدردشة بنجاح.")
        return

    # Activity stats
    if any(cmd in text.lower() for cmd in ["المتفاعلين", "تفاعل"]):
        if not is_admin(update, context): 
            msg.reply_text(random.choice(NOT_ADMIN_REPLIES))
            return
        
        week_ago = time.time() - (7*24*3600)
        stats = []
        for uid, ts in user_activity.items():
            count = len([t for t in ts if t > week_ago])
            if count > 0:
                try:
                    member = chat.get_member(uid)
                    name = member.user.full_name
                    stats.append((name, count))
                except:
                    stats.append((f"مستخدم {uid}", count))
        
        stats.sort(key=lambda x: x[1], reverse=True)
        top_stats = stats[:10]
        report = "📊 أكثر المتفاعلين (أسبوع):\n\n" + "\n".join([f"{i+1}. {n} - {c}" for i, (n,c) in enumerate(top_stats)]) if top_stats else "لا يوجد تفاعل."
        msg.reply_text(report, parse_mode='Markdown')
        return

    # User Management Commands
    admin_keywords = ["كتم", "طرد", "رفع", "ارفع", "حذف كتم", "اكتمه", "سكته", "اطرده", "اطلع بره"]
    if any(cmd in text.lower() for cmd in admin_keywords):
        # Requirement: Non-admin using these keywords WITHOUT reply should be ignored
        if not is_admin(update, context) and not msg.reply_to_message:
            return
            
        # Requirement: Management keywords MUST be used as a reply to be recognized
        if not msg.reply_to_message:
            return

        # Show "not admin" if a non-admin uses it as a reply
        if not is_admin(update, context):
            msg.reply_text(random.choice(NOT_ADMIN_REPLIES))
            return

        target_user = msg.reply_to_message.from_user
        if any(cmd in text.lower() for cmd in ["رفع", "ارفع", "حذف كتم"]):
            try:
                context.bot.restrict_chat_member(GROUP_ID, target_user.id, ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True, can_add_web_page_previews=True, can_send_polls=True, can_pin_messages=True, can_change_info=True))
                msg.reply_text(f"✅ تم رفع الكتم: @{target_user.username or target_user.first_name}")
            except Exception as e:
                logging.error(f"Unmute error: {e}")
        elif any(cmd in text.lower() for cmd in ["كتم", "اكتمه", "سكته"]):
            try:
                context.bot.restrict_chat_member(GROUP_ID, target_user.id, ChatPermissions(can_send_messages=False))
                msg.reply_text(f"🔇 تم الكتم: @{target_user.username or target_user.first_name}")
            except Exception as e:
                logging.error(f"Mute error: {e}")
        elif any(cmd in text.lower() for cmd in ["طرد", "اطرده", "اطلع بره"]):
            try:
                context.bot.kick_chat_member(GROUP_ID, target_user.id, revoke_messages=True)
                msg.reply_text(f"{random.choice(KICK_REPLIES)}: @{target_user.username or target_user.first_name}")
            except Exception as e:
                logging.error(f"Kick error: {e}")

def keyword_replies(update: Update, context: CallbackContext):
    global is_chat_locked
    chat = update.effective_chat
    msg = update.message
    if not chat or chat.id != GROUP_ID or not msg or not msg.text:
        return
    
    # Don't reply if chat is locked and user is not admin
    if is_chat_locked and not is_admin(update, context):
        return

    text = msg.text.lower().strip()
    
    if re.search(r"(اوراس|وراس|أسو|اسو)", text):
        msg.reply_text(random.choice(ORAS_RANDOM_REPLIES), quote=True)
        context.job_queue.run_once(lambda x: context.bot.send_sticker(GROUP_ID, ORAS_STICKER), 1)
        return
    if re.search(r"(عيونها|عيونه)", text):
        msg.reply_text(random.choice(EYES_RANDOM_REPLIES), quote=True)
        context.job_queue.run_once(lambda x: context.bot.send_sticker(GROUP_ID, EYES_STICKER), 1)
        return
        
    for pattern, replies in KEYWORD_REPLIES.items():
        if re.search(pattern, text):
            if any(p in pattern for p in ["بوت", "احبك"]):
                time.sleep(2)
            msg.reply_text(random.choice(replies), quote=True)
            return

def main():
    if not TOKEN:
        logging.error("TELEGRAM_BOT_TOKEN not found in environment variables.")
        return

    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(MessageHandler(Filters.all & ~Filters.command, track_activity), group=0)
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, admin_actions), group=1)
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, keyword_replies), group=2)
    dp.add_handler(ChatMemberHandler(track_activity), group=3)

    logging.info("Bot started...")
    updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    updater.idle()

if __name__ == '__main__':
    main()
