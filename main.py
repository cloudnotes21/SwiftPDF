import os
from io import BytesIO
from PIL import Image, ImageEnhance
from fpdf import FPDF
import fitz  # PyMuPDF
import telebot
from telebot import types

API_TOKEN = os.getenv("API_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = telebot.TeleBot(API_TOKEN)
user_sessions = {}

# Ensure download folder exists
if not os.path.exists("downloads"):
    os.makedirs("downloads")

def main_menu(pdf_received=False):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('✅ Done')
    if pdf_received:
        markup.row('📂 Extract Images')
    return markup

@bot.message_handler(commands=['start'])
def cmd_start(m):
    user_sessions.pop(m.from_user.id, None)
    bot.send_message(m.chat.id, "👋 Welcome! Send photos to convert to PDF or PDF to extract images.", 
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
        elif m.document.mime_type in ["image/jpeg", "image/png"]:
            session['photos'].append(m.document.file_id)
            bot.send_message(sid, f"✅ Photo added ({len(session['photos'])}).", reply_markup=main_menu(bool(session['pdf'])))
        else:
            bot.send_message(sid, "❗ Only PDF or image documents allowed.", reply_markup=main_menu(bool(session['pdf'])))

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

@bot.message_handler(func=lambda m: m.text in ['🖤 Black & White','✨ Contrast'])
def apply_filter_and_send(m):
    sid = m.from_user.id
    session = user_sessions.get(sid)
    choice = m.text
    photos = session.get('photos', [])
    if not photos or session.get('state')!='awaiting_filter':
        return

    images = []
    for fid in photos:
        file = bot.get_file(fid)
        downloaded = bot.download_file(file.file_path)
        img = Image.open(BytesIO(downloaded)).convert('RGB')
        if choice == '🖤 Black & White':
            img = img.convert('L').convert('RGB')
        else:
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.5)
        images.append(img)

    pdf_io = BytesIO()
    images[0].save(pdf_io, format='PDF', save_all=True, append_images=images[1:])
    pdf_io.seek(0)
    bot.send_document(sid, pdf_io, caption="📄 Here is your PDF!", reply_markup=main_menu(pdf_received=bool(session.get('pdf'))))
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

    pdf_path = f"downloads/{sid}_temp.pdf"
    with open(pdf_path, 'wb') as f:
        f.write(file_data)

    bot.send_message(sid, "🔍 Extracting images...")
    doc = fitz.open(pdf_path)
    image_paths = []
    for page_index in range(len(doc)):
        for img_index, img in enumerate(doc.get_page_images(page_index)):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image['image']
            ext = base_image['ext']
            img_buf = BytesIO(image_bytes)
            img_buf.seek(0)
            bot.send_photo(sid, img_buf)
    doc.close()
    os.remove(pdf_path)

    session['pdf'] = None
    bot.send_message(sid, "✅ Done!", reply_markup=main_menu())

print("🤖 Bot is running...")
bot.infinity_polling()
