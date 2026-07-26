from functools import wraps
def is_authorized(user_id:int|None,allowed:set[int])->bool: return user_id is not None and user_id in allowed
def authorized(handler):
    @wraps(handler)
    async def wrapped(update,context):
        settings=context.application.bot_data["settings"]; uid=update.effective_user.id if update.effective_user else None
        if not is_authorized(uid,settings.telegram_allowed_user_ids):
            if update.effective_message: await update.effective_message.reply_text("Acceso no autorizado.")
            return None
        return await handler(update,context)
    return wrapped
