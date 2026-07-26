from telegram import InlineKeyboardButton,InlineKeyboardMarkup
def preview_keyboard(import_id: int | None = None):
    suffix = f":{import_id}" if import_id is not None else ""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📷 Asignar foto",callback_data=f"assign_photo{suffix}")],
        [InlineKeyboardButton("Crear borrador",callback_data=f"create{suffix}"),InlineKeyboardButton("Cancelar",callback_data=f"cancel{suffix}")],
        [InlineKeyboardButton("Crear y publicar",callback_data=f"create_publish_request{suffix}")],
        [InlineKeyboardButton("Editar título",callback_data="edit_title"),InlineKeyboardButton("Editar precio",callback_data="edit_price")],
        [InlineKeyboardButton("Editar descripción",callback_data="edit_description"),InlineKeyboardButton("Cambiar recargo",callback_data="edit_markup")]])


def photo_confirmation_keyboard(import_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Usar esta foto",callback_data=f"photo_confirm:{import_id}")],
        [InlineKeyboardButton("🔄 Cambiar foto",callback_data=f"assign_photo:{import_id}")],
        [InlineKeyboardButton("❌ Cancelar",callback_data=f"photo_cancel:{import_id}")],
    ])


def publish_keyboard(import_id: int):
    return InlineKeyboardMarkup([[InlineKeyboardButton(
        "Publicar en tienda online", callback_data=f"publish_request:{import_id}"
    )]])


def publish_confirmation_keyboard(import_id: int):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Sí, publicar ahora", callback_data=f"publish_confirm:{import_id}"),
        InlineKeyboardButton("No", callback_data=f"publish_cancel:{import_id}"),
    ]])


def create_publish_confirmation_keyboard(import_id: int):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "Sí, crear y publicar", callback_data=f"create_publish_confirm:{import_id}"
        ),
        InlineKeyboardButton("No", callback_data=f"publish_cancel:{import_id}"),
    ]])
