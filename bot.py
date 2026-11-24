last_error_time = {}

def should_respond(update, context):
    message = update.message
    if not message:
        return False

    # در گفت‌وگوی خصوصی همیشه پاسخ بده
    if update.effective_chat.type == "private":
        return True

    bot_id = context.bot.id
    bot_username = context.bot.username

    # اگر کاربر به پیام خود ربات ریپلای کرده باشد
    if message.reply_to_message:
        replied_user = message.reply_to_message.from_user
        if replied_user and replied_user.id == bot_id:
            return True

    # اگر کاربر نام کاربری ربات را صدا زده باشد
    if bot_username:
        pattern = rf"@{re.escape(bot_username)}\b"
        if re.search(pattern, message.text or "", re.IGNORECASE):
            return True

    return False
