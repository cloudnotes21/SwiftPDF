import os
from io import BytesIO
from PIL import Image
from PyPDF2 import PdfReader
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
def cmd_start(m):
    user_sessions.pop(m.from_user.id, None)
    bot.send_message(m.chat.id, "👋 Welcome! Send photos (as file or photo) to convert into PDF.\nYou can also send a PDF to extract images from it.", reply_markup=main_menu())

@bot.message_handler(content_types=['photo', 'document'])
def handle_input(m):
    sid = m.from_user.id
    session = user_sessions.setdefault(sid, {'photos': [], 'pdf': None})

    if m.content_type == 'photo':
        # Compressed photo
        file_id = m.photo[-1].file_id
        session['photos'].append(file_id)
        bot.send_message(sid, f"✅ Photo added ({len(session['photos'])}).", reply_markup=main_menu(bool(session['pdf'])))
    elif m.content_type == 'document':
        if m.document.mime_type == 'application/pdf':
            session['pdf'] = m.document.file_id
            bot.send_message(sid, "📄 PDF received.", reply_markup=main_menu(pdf_received=True))
        elif m.document.mime_type in ['image/jpeg', 'image/png']:
            session['photos'].append(m.document.file_id)
            bot.send_message(sid, f"✅ Image added ({len(session['photos'])}).", reply_markup=main_menu(bool(session['pdf'])))
        else:
            bot.send_message(sid, "❗ Only PDF, JPEG or PNG images are allowed.", reply_markup=main_menu(bool(session['pdf'])))

@bot.message_handler(func=lambda m: m.text == '✅ Done')
def build_pdf(m):
    sid = m.from_user.id
    session = user_sessions.get(sid)
    if not session or not session['photos']:
        bot.send_message(sid, "❗ No images to convert.", reply_markup=main_menu(bool(session.get('pdf'))))
        return

    images = []
    for fid in session['photos']:
        try:
            file_info = bot.get_file(fid)
            file_data = bot.download_file(file_info.file_path)
            img = Image.open(BytesIO(file_data)).convert('RGB')
            images.append(img)
        except Exception as e:
            bot.send_message(sid, f"❗ Error loading image: {e}")

    if not images:
        bot.send_message(sid, "⚠️ No valid images to generate PDF.", reply_markup=main_menu())
        return

    output = BytesIO()
    images[0].save(output, format='PDF', save_all=True, append_images=images[1:])
    output.seek(0)
    bot.send_document(sid, output, caption="📄 Here is your PDF!", reply_markup=main_menu(pdf_received=bool(session.get('pdf'))))
    session['photos'] = []

@bot.message_handler(func=lambda m: m.text == '📂 Extract Images')
def extract_images(m):
    sid = m.from_user.id
    session = user_sessions.get(sid)
    if not session or not session.get('pdf'):
        bot.send_message(sid, "❗ No PDF to extract images from.", reply_markup=main_menu())
        return

    try:
        file_info = bot.get_file(session['pdf'])
        file_data = bot.download_file(file_info.file_path)
        reader = PdfReader(BytesIO(file_data))
        count = 0

        for i, page in enumerate(reader.pages):
            if '/XObject' in page.get('/Resources', {}):
                xObject = page['/Resources']['/XObject'].get_object()
                for obj in xObject:
                    if xObject[obj]['/Subtype'] == '/Image':
                        size = (xObject[obj]['/Width'], xObject[obj]['/Height'])
                        data = xObject[obj].get_data()
                        mode = "RGB" if xObject[obj]['/ColorSpace'] == '/DeviceRGB' else "P"
                        img = Image.frombytes(mode, size, data)
                        buf = BytesIO()
                        img.save(buf, format='PNG')
                        buf.seek(0)
                        bot.send_photo(sid, buf)
                        count += 1

        if count == 0:
            bot.send_message(sid, "⚠️ No images found in that PDF.")
        else:
            bot.send_message(sid, f"✅ Done! Extracted {count} images.")

    except Exception as e:
        bot.send_message(sid, f"❌ Failed to extract images: {e}")
    
    session['pdf'] = None

bot.infinity_polling()
