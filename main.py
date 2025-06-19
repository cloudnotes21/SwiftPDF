# Updated Telegram bot to handle:
# 1. Image to PDF conversion with filters.
# 2. 'Done' button in the menu for PDF generation.
# 3. If a PDF is uploaded, show 'Extract Images' option only.

import os
import telebot
from telebot import types
from PIL import Image, ImageEnhance
from PyPDF2 import PdfReader
from io import BytesIO
import requests

API_TOKEN = os.getenv("API_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = telebot.TeleBot(API_TOKEN)

user_sessions = {}

# Menu keyboard
main_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
main_keyboard.add("Done")

filter_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
filter_keyboard.add("Normal", "Black & White", "Contrast Boost")

# Image processing filters
def apply_filter(image, mode):
    if mode == "Black & White":
        return image.convert('L').convert("RGB")
    elif mode == "Contrast Boost":
        enhancer = ImageEnhance.Contrast(image)
        return enhancer.enhance(2.0)
    return image

@bot.message_handler(commands=['start'])
def welcome(message):
    bot.send_message(message.chat.id, "👋 Welcome! Send images to convert them into a PDF or upload a PDF to extract images.")

@bot.message_handler(content_types=['photo', 'document'])
def handle_files(message):
    user_id = message.from_user.id
    if user_id not in user_sessions:
        user_sessions[user_id] = {"images": [], "status": None}
    session = user_sessions[user_id]

    if message.content_type == 'photo':
        file_id = message.photo[-1].file_id
        session["images"].append(file_id)
        session["status"] = "collecting"
        bot.send_message(user_id, f"✅ Image {len(session['images'])} received. Click 'Done' when ready.", reply_markup=main_keyboard)

    elif message.content_type == 'document':
        mime = message.document.mime_type
        if mime == 'application/pdf':
            keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
            keyboard.add("Extract Images")
            session["status"] = "pdf_uploaded"
            session["pdf_file"] = message.document.file_id
            bot.send_message(user_id, "📄 PDF received. What would you like to do?", reply_markup=keyboard)
        else:
            bot.send_message(user_id, "❗️ Only PDFs are supported for extraction.")

@bot.message_handler(func=lambda m: m.text == "Done")
def done_collecting(message):
    user_id = message.from_user.id
    session = user_sessions.get(user_id)

    if not session or not session.get("images"):
        bot.send_message(user_id, "❗️ You haven't sent any images yet.")
        return

    session["status"] = "awaiting_filter"
    bot.send_message(user_id, "🎨 Choose a filter to apply before creating your PDF:", reply_markup=filter_keyboard)

@bot.message_handler(func=lambda m: m.text in ["Normal", "Black & White", "Contrast Boost"])
def generate_pdf(message):
    user_id = message.from_user.id
    session = user_sessions.get(user_id)

    if not session or session["status"] != "awaiting_filter":
        return

    filter_choice = message.text
    images = []

    for file_id in session["images"]:
        file_info = bot.get_file(file_id)
        file_data = requests.get(f"https://api.telegram.org/file/bot{API_TOKEN}/{file_info.file_path}").content
        img = Image.open(BytesIO(file_data)).convert("RGB")
        filtered_img = apply_filter(img, filter_choice)
        images.append(filtered_img)

    if images:
        pdf_bytes = BytesIO()
        images[0].save(pdf_bytes, format="PDF", save_all=True, append_images=images[1:])
        pdf_bytes.seek(0)
        bot.send_document(user_id, pdf_bytes, visible_file_name="converted.pdf")
        bot.send_message(user_id, "✅ Your PDF has been created successfully.")
        user_sessions.pop(user_id)
    else:
        bot.send_message(user_id, "❗️ Failed to create PDF.")

@bot.message_handler(func=lambda m: m.text == "Extract Images")
def extract_images(message):
    user_id = message.from_user.id
    session = user_sessions.get(user_id)
    if not session or "pdf_file" not in session:
        bot.send_message(user_id, "❗️ No PDF file found to extract.")
        return

    file_id = session["pdf_file"]
    file_info = bot.get_file(file_id)
    file_data = requests.get(f"https://api.telegram.org/file/bot{API_TOKEN}/{file_info.file_path}").content

    temp_path = f"temp_{user_id}.pdf"
    with open(temp_path, 'wb') as f:
        f.write(file_data)

    reader = PdfReader(temp_path)
    count = 0
    for i, page in enumerate(reader.pages):
        if '/XObject' in page['/Resources']:
            xObject = page['/Resources']['/XObject'].get_object()
            for obj in xObject:
                if xObject[obj]['/Subtype'] == '/Image':
                    size = (xObject[obj]['/Width'], xObject[obj]['/Height'])
                    data = xObject[obj].get_data()
                    img = Image.frombytes('RGB', size, data)
                    bio = BytesIO()
                    img.save(bio, format='JPEG')
                    bio.seek(0)
                    bot.send_photo(user_id, photo=bio)
                    count += 1

    os.remove(temp_path)
    bot.send_message(user_id, f"🖼 Extracted {count} image(s) from your PDF.")
    user_sessions.pop(user_id, None)

print("🤖 PDF Bot running...")
bot.infinity_polling()
