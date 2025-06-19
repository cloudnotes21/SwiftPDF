import telebot
from telebot import types
from io import BytesIO
from PIL import Image, ImageEnhance
from fpdf import FPDF
from PyPDF2 import PdfReader

API_TOKEN = '8047121156:AAERsQie1NWmWw3VAlQVMZ0WZz4nDrJ5S8I'
ADMIN_ID = 1973627200

bot = telebot.TeleBot(API_TOKEN)
user_sessions = {}

def main_menu(pdf_received=False):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('🖼️ Add Photo', '✅ Done')
    if pdf_received:
        markup.row('📂 Extract Images')
    return markup

@bot.message_handler(commands=['start'])
def cmd_start(m):
    user_sessions.pop(m.from_user.id, None)
    bot.send_message(m.chat.id, "👋 Welcome! Use the menu to add photos or extract images from PDF.", 
                     reply_markup=main_menu())

@bot.message_handler(content_types=['photo', 'document'])
def handle_input(m):
    sid = m.from_user.id
    session = user_sessions.setdefault(sid, {'photos': [], 'pdf': None})

    if m.content_type == 'photo':
        session['photos'].append(m.photo[-1].file_id)
        bot.send_message(sid, f"✅ Photo added ({len(session['photos'])}).", reply_markup=main_menu(bool(session['pdf'])))
    else:  # document
        if m.document.mime_type == 'application/pdf':
            session['pdf'] = m.document.file_id
            bot.send_message(sid, "📄 PDF received.", reply_markup=main_menu(pdf_received=True))
        else:
            bot.send_message(sid, "❗ Only PDF documents allowed.", reply_markup=main_menu(bool(session['pdf'])))

@bot.message_handler(func=lambda m: m.text == '✅ Done')
def build_pdf(m):
    sid = m.from_user.id
    session = user_sessions.get(sid)
    if not session or not session['photos']:
        bot.send_message(sid, "❗ No photos to convert.", reply_markup=main_menu(bool(session.get('pdf'))))
        return

    session['state'] = 'awaiting_filter'
    bot.send_message(sid, "🎨 Choose a filter:", 
                     reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).row('🖤 Black & White', '✨ Contrast'))

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
        img = Image.open(BytesIO(bot.download_file(file.file_path))).convert('RGB')
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
    file = bot.get_file(session['pdf'])
    reader = PdfReader(BytesIO(bot.download_file(file.file_path)))
    imgs = []
    for p in reader.pages:
        for obj in p.images.values():
            data = obj.data
            img = Image.open(BytesIO(data))
            imgs.append(img)
    if imgs:
        for img in imgs:
            buf = BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)
            bot.send_photo(sid, buf)
    else:
        bot.send_message(sid, "⚠️ No images found in that PDF.")
    session['pdf'] = None
    bot.send_message(sid, "Done!", reply_markup=main_menu())

bot.infinity_polling()
