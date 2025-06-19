import os
from io import BytesIO
from PIL import Image, ImageEnhance
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
    bot.send_message(m.chat.id, "👋 Welcome! Send photos (as photo or document) to convert to PDF or PDF to extract images.",
                     reply_markup=main_menu())

@bot.message_handler(content_types=['photo', 'document'])
def handle_input(m):
    sid = m.from_user.id
    session = user_sessions.setdefault(sid, {'photos': [], 'pdf': None})

    if m.content_type == 'photo':
        session['photos'].append(m.photo[-1].file_id)
        bot.send_message(sid, f"✅ Photo added ({len(session['photos'])}).", reply_markup=main_menu(bool(session['pdf'])))
    elif m.content_type == 'document':
        if m.document.mime_type == 'application/pdf':
            session['pdf'] = m.document.file_id
            bot.send_message(sid, "📄 PDF received.", reply_markup=main_menu(pdf_received=True))
        elif m.document.mime_type in ['image/jpeg', 'image/png']:
            session['photos'].append(m.document.file_id)
            bot.send_message(sid, f"✅ Image added ({len(session['photos'])}).", reply_markup=main_menu(bool(session['pdf'])))
        else:
            bot.send_message(sid, "❗ Only PDF, JPEG or PNG images allowed.", reply_markup=main_menu(bool(session['pdf'])))

@bot.message_handler(func=lambda m: m.text == '✅ Done')
def build_pdf(m):
    sid = m.from_user.id
    session = user_sessions.get(sid)
    if not session or not session['photos']:
        bot.send_message(sid, "❗ No photos to convert.", reply_markup=main_menu(bool(session.get('pdf'))))
        return

    session['state'] = 'awaiting_filter'
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('🖤 Black & White', '✨ Contrast')
    bot.send_message(sid, "🎨 Choose a filter:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text in ['🖤 Black & White', '✨ Contrast'])
def apply_filter_and_send(m):
    sid = m.from_user.id
    session = user_sessions.get(sid)
    photos = session.get('photos', [])
    if not photos or session.get('state') != 'awaiting_filter':
        return

    images = []
    for fid in photos:
        file_info = bot.get_file(fid)
        file_data = bot.download_file(file_info.file_path)
        try:
            img = Image.open(BytesIO(file_data)).convert('RGB')
        except Exception as e:
            bot.send_message(sid, f"❗ Error reading an image: {e}")
            continue

        if m.text == '🖤 Black & White':
            img = img.convert('L').convert('RGB')
        elif m.text == '✨ Contrast':
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.5)

        images.append(img)

    if not images:
        bot.send_message(sid, "⚠️ No valid images to generate PDF.", reply_markup=main_menu())
        return

    pdf_buffer = BytesIO()
    images[0].save(pdf_buffer, format='PDF', save_all=True, append_images=images[1:])
    pdf_buffer.seek(0)

    bot.send_document(sid, pdf_buffer, caption="📄 Here is your PDF!", reply_markup=main_menu(pdf_received=bool(session.get('pdf'))))
    session['photos'] = []
    session.pop('state', None)

@bot.message_handler(func=lambda m: m.text == '📂 Extract Images')
def extract_images(m):
    sid = m.from_user.id
    session = user_sessions.get(sid)
    if not session or not session.get('pdf'):
        bot.send_message(sid, "❗ No PDF to extract images from.", reply_markup=main_menu())
        return

    file_info = bot.get_file(session['pdf'])
    file_data = bot.download_file(file_info.file_path)

    reader = PdfReader(BytesIO(file_data))
    count = 0
    for page in reader.pages:
        if '/XObject' in page['/Resources']:
            xObject = page['/Resources']['/XObject'].get_object()
            for obj in xObject:
                if xObject[obj]['/Subtype'] == '/Image':
                    size = (xObject[obj]['/Width'], xObject[obj]['/Height'])
                    data = xObject[obj].get_data()
                    mode = "RGB"
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
    session['pdf'] = None

bot.infinity_polling()
