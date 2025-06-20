import os
import threading
import time
from io import BytesIO
import fitz  # PyMuPDF
from PIL import Image
import telebot
from telebot import types
from telebot.types import InputFile

API_TOKEN = '8047121156:AAERsQie1NWmWw3VAlQVMZ0WZz4nDrJ5S8I'  # ← apna Telegram bot token yahan daalein
bot = telebot.TeleBot(API_TOKEN)
user_sessions = {}

# Emojis for animated status
EMOJIS = ['🤪','🧐','🤓','😎','🥸','🤩','🙃','😉','☺️','😇']

def main_menu(images_present=False, pdf_received=False):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if images_present:
        markup.row('✅ Done')
    if pdf_received:
        markup.row('📂 Extract Images')
    return markup

def animate_status(bot, chat_id, text, stop_event):
    """
    Animates a message with changing emojis every 0.4s until stop_event is set.
    Returns the sent message object.
    """
    msg = bot.send_message(chat_id, f"{text} {EMOJIS[0]}")
    i = 1
    while not stop_event.is_set():
        try:
            bot.edit_message_text(f"{text} {EMOJIS[i % len(EMOJIS)]}", chat_id, msg.message_id)
        except Exception:
            pass  # Ignore edit errors (e.g., message deleted)
        time.sleep(0.4)
        i += 1
    return msg

@bot.message_handler(commands=['start'])
def start_bot(message):
    user_sessions[message.chat.id] = {'images': [], 'pdf_file_id': None}
    bot.send_message(
        message.chat.id,
        "👋 Send images (photo or image document) to create PDF.\nOr send a PDF to extract images.",
        reply_markup=main_menu()
    )

@bot.message_handler(content_types=['photo', 'document'])
def handle_files(message):
    cid = message.chat.id
    session = user_sessions.setdefault(cid, {'images': [], 'pdf_file_id': None})

    if message.content_type == 'photo':
        file_id = message.photo[-1].file_id
        session['images'].append(file_id)
    elif message.document:
        mime = message.document.mime_type
        if mime in ['image/jpeg', 'image/png']:
            session['images'].append(message.document.file_id)
        elif mime == 'application/pdf':
            session['pdf_file_id'] = message.document.file_id

    images_present = len(session['images']) > 0
    pdf_received = session.get('pdf_file_id') is not None

    bot.send_message(
        cid,
        "File received.",
        reply_markup=main_menu(images_present=images_present, pdf_received=pdf_received)
    )

@bot.message_handler(func=lambda m: m.text == '✅ Done')
def generate_pdf(message):
    cid = message.chat.id
    session = user_sessions.get(cid)
    if not session or not session['images']:
        bot.send_message(cid, "❗ No images to convert.", reply_markup=main_menu())
        return

    # Start emoji animation in thread
    stop_event = threading.Event()
    anim_thread = threading.Thread(target=animate_status, args=(bot, cid, "Generating PDF...", stop_event))
    anim_thread.start()

    images = []
    for file_id in session['images']:
        file_info = bot.get_file(file_id)
        file_data = bot.download_file(file_info.file_path)
        try:
            image = Image.open(BytesIO(file_data)).convert('RGB')
            images.append(image)
        except:
            pass

    # Stop emoji animation
    stop_event.set()
    anim_thread.join()

    if not images:
        bot.send_message(cid, "❗ No valid images to create PDF.", reply_markup=main_menu())
        return

    output = BytesIO()
    images[0].save(output, format='PDF', save_all=True, append_images=images[1:])
    output.seek(0)

    try:
        input_file = InputFile(output, "converted.pdf")
        bot.send_document(
            cid,
            input_file,
            caption="📄 Your PDF is ready!"
        )
    except Exception as e:
        bot.send_message(cid, f"❌ Error sending PDF: {e}")

    session['images'] = []
    # Update menu
    images_present = len(session['images']) > 0
    pdf_received = session.get('pdf_file_id') is not None
    bot.send_message(cid, "Done!", reply_markup=main_menu(images_present=images_present, pdf_received=pdf_received))

@bot.message_handler(func=lambda m: m.text == '📂 Extract Images')
def extract_images_from_pdf(message):
    cid = message.chat.id
    session = user_sessions.get(cid)
    if not session or not session.get('pdf_file_id'):
        bot.send_message(cid, "❗ No PDF uploaded.", reply_markup=main_menu())
        return

    # Start emoji animation in thread
    stop_event = threading.Event()
    anim_thread = threading.Thread(target=animate_status, args=(bot, cid, "Extracting images...", stop_event))
    anim_thread.start()

    try:
        file_info = bot.get_file(session['pdf_file_id'])
        file_data = bot.download_file(file_info.file_path)

        doc = fitz.open(stream=file_data, filetype='pdf')
        count = 0

        for i in range(len(doc)):
            for img in doc.get_page_images(i):
                xref = img[0]
                base_image = doc.extract_image(xref)
                img_bytes = base_image["image"]
                img_io = BytesIO(img_bytes)
                img_io.seek(0)
                bot.send_photo(cid, img_io)
                count += 1

        msg = f"✅ Done! Extracted {count} image(s)." if count else "⚠️ No images found."
        # Stop emoji animation
        stop_event.set()
        anim_thread.join()
        bot.send_message(cid, msg)
        session['pdf_file_id'] = None
    except Exception as e:
        stop_event.set()
        anim_thread.join()
        bot.send_message(cid, f"❌ Error: {e}")

    # Update menu
    images_present = len(session['images']) > 0
    pdf_received = session.get('pdf_file_id') is not None
    bot.send_message(cid, "Done!", reply_markup=main_menu(images_present=images_present, pdf_received=pdf_received))

bot.infinity_polling()
