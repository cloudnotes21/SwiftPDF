import os
from io import BytesIO
import fitz  # PyMuPDF
from PIL import Image
import telebot
from telebot import types

API_TOKEN = '8047121156:AAERsQie1NWmWw3VAlQVMZ0WZz4nDrJ5S8I'
ADMIN_ID = 1973627200

bot = telebot.TeleBot(API_TOKEN)
user_sessions = {}

def main_menu(pdf_received=False):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('✅ Done')
    if pdf_received:
        markup.row('📂 Extract Images')
    return markup

@bot.message_handler(commands=['start'])
def start_bot(message):
    user_sessions[message.chat.id] = {'images': [], 'pdf_file_id': None}
    bot.send_message(message.chat.id,
        "👋 Send images (as photo or image document) to convert into PDF.\n"
        "Or send a PDF to extract images from it.",
        reply_markup=main_menu()
    )

@bot.message_handler(content_types=['photo', 'document'])
def handle_files(message):
    cid = message.chat.id
    session = user_sessions.setdefault(cid, {'images': [], 'pdf_file_id': None})

    if message.content_type == 'photo':
        file_id = message.photo[-1].file_id
        session['images'].append(file_id)
        bot.send_message(cid, f"✅ Photo added ({len(session['images'])})", reply_markup=main_menu())

    elif message.document:
        if message.document.mime_type in ['image/jpeg', 'image/png']:
            session['images'].append(message.document.file_id)
            bot.send_message(cid, f"✅ Image added ({len(session['images'])})", reply_markup=main_menu())
        elif message.document.mime_type == 'application/pdf':
            session['pdf_file_id'] = message.document.file_id
            bot.send_message(cid, "📄 PDF received.", reply_markup=main_menu(pdf_received=True))
        else:
            bot.send_message(cid, "❗ Please send only JPEG/PNG images or PDF files.")

@bot.message_handler(func=lambda m: m.text == '✅ Done')
def generate_pdf(message):
    cid = message.chat.id
    session = user_sessions.get(cid)
    if not session or not session['images']:
        bot.send_message(cid, "❗ No images to convert.", reply_markup=main_menu())
        return

    images = []
    for file_id in session['images']:
        file_info = bot.get_file(file_id)
        file_data = bot.download_file(file_info.file_path)
        try:
            image = Image.open(BytesIO(file_data)).convert('RGB')
            images.append(image)
        except:
            bot.send_message(cid, "⚠️ Could not open one of the images. Skipping.")

    if not images:
        bot.send_message(cid, "❗ No valid images to create PDF.")
        return

    output = BytesIO()
    images[0].save(output, format='PDF', save_all=True, append_images=images[1:])
    output.seek(0)

    bot.send_document(cid, output, caption="📄 Your PDF is ready!")
    session['images'] = []

@bot.message_handler(func=lambda m: m.text == '📂 Extract Images')
def extract_images_from_pdf(message):
    cid = message.chat.id
    session = user_sessions.get(cid)
    if not session or not session.get('pdf_file_id'):
        bot.send_message(cid, "❗ No PDF uploaded to extract images.", reply_markup=main_menu())
        return

    file_info = bot.get_file(session['pdf_file_id'])
    file_data = bot.download_file(file_info.file_path)

    doc = fitz.open(stream=file_data, filetype='pdf')
    count = 0

    for page_index in range(len(doc)):
        images = doc.get_page_images(page_index)
        for img_index, img in enumerate(images):
            xref = img[0]
            base_image = doc.extract_image(xref)
            img_bytes = base_image["image"]
            img_ext = base_image["ext"]
            img_io = BytesIO(img_bytes)
            img_io.seek(0)
            bot.send_photo(cid, img_io)
            count += 1

    if count == 0:
        bot.send_message(cid, "⚠️ No images found in the PDF.")
    else:
        bot.send_message(cid, f"✅ Done! Extracted {count} image(s).")

    session['pdf_file_id'] = None

bot.infinity_polling()
