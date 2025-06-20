import os
import threading
import time
from io import BytesIO
import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont
import telebot
from telebot import types
from telebot.types import InputFile

API_TOKEN = '8047121156:AAERsQie1NWmWw3VAlQVMZ0WZz4nDrJ5S8I'
bot = telebot.TeleBot(API_TOKEN)
user_sessions = {}

# Emojis for animated status
EMOJIS = ['🤪','🧐','🤓','😎','🥸','🤩','🙃','😉','☺️','😇']

# Font for text rendering (ensure this file is present in your project directory)
FONT_PATH = "DejaVuSans.ttf"  # Use a bundled open font for Railway. Copy DejaVuSans.ttf to your project!

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
    """
    msg = bot.send_message(chat_id, f"{text} {EMOJIS[0]}")
    i = 1
    while not stop_event.is_set():
        try:
            bot.edit_message_text(f"{text} {EMOJIS[i % len(EMOJIS)]}", chat_id, msg.message_id)
        except Exception:
            pass
        time.sleep(0.2)
        i += 1

def text_to_a4_images(text, font_path=FONT_PATH, font_size=30, margin=60):
    """
    Converts long text to one or more A4-sized images with proper word wrapping.
    Returns list of BytesIO image objects.
    """
    # A4 at 150 dpi: 1240 x 1754 px
    A4 = (1240, 1754)
    try:
        font = ImageFont.truetype(font_path, font_size)
    except Exception:
        font = ImageFont.load_default()
    lines = []

    # Word wrap
    dummy_img = Image.new("RGB", A4, "white")
    draw = ImageDraw.Draw(dummy_img)
    max_width = A4[0] - 2 * margin

    for paragraph in text.split('\n'):
        line = ''
        for word in paragraph.split(' '):
            test_line = line + (' ' if line else '') + word
            w, _ = draw.textsize(test_line, font=font)
            if w <= max_width:
                line = test_line
            else:
                lines.append(line)
                line = word
        if line:
            lines.append(line)
        lines.append('')  # paragraph break

    # Paginate
    images = []
    y_start = margin
    y = y_start
    page = Image.new("RGB", A4, "white")
    draw = ImageDraw.Draw(page)
    for line in lines:
        w, h = draw.textsize(line, font=font)
        if y + h > A4[1] - margin:
            output = BytesIO()
            page.save(output, format="JPEG")
            output.seek(0)
            images.append(output)
            page = Image.new("RGB", A4, "white")
            draw = ImageDraw.Draw(page)
            y = y_start
        draw.text((margin, y), line, fill="black", font=font)
        y += h + 8  # line spacing
    # Last page
    output = BytesIO()
    page.save(output, format="JPEG")
    output.seek(0)
    images.append(output)
    return images

@bot.message_handler(commands=['start'])
def start_bot(message):
    user_sessions[message.chat.id] = {'images': [], 'pdf_file_id': None}
    bot.send_message(
        message.chat.id,
        "👋 Send images (photo or image document) to create PDF.\nOr send a PDF to extract images (images or text will be sent as A4-sized images).",
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

    stop_event = threading.Event()
    anim_thread = threading.Thread(target=animate_status, args=(bot, cid, "Extracting images...", stop_event))
    anim_thread.start()

    try:
        file_info = bot.get_file(session['pdf_file_id'])
        file_data = bot.download_file(file_info.file_path)

        doc = fitz.open(stream=file_data, filetype='pdf')
        count = 0
        text_pages = []

        for page_num in range(len(doc)):
            images_found = False
            for img in doc.get_page_images(page_num):
                xref = img[0]
                base_image = doc.extract_image(xref)
                img_bytes = base_image["image"]
                img_io = BytesIO(img_bytes)
                img_io.seek(0)
                bot.send_photo(cid, img_io)
                count += 1
                images_found = True
            if not images_found:
                # If no images, extract text and render as image
                text = doc.load_page(page_num).get_text()
                if text.strip():
                    text_pages.append(text)

        if count == 0 and text_pages:
            bot.send_message(cid, "No images found, sending document text as A4-sized images.")
            for idx, text in enumerate(text_pages):
                images = text_to_a4_images(text)
                for imgb in images:
                    imgb.seek(0)
                    bot.send_photo(cid, imgb, caption=f"Page {idx+1}")

        msg = f"✅ Done! Extracted {count} image(s)." if count else f"✅ Done! Sent {len(text_pages)} text page(s) as images."
        stop_event.set()
        anim_thread.join()
        bot.send_message(cid, msg)
        session['pdf_file_id'] = None
    except Exception as e:
        stop_event.set()
        anim_thread.join()
        bot.send_message(cid, f"❌ Error: {e}")

    images_present = len(session['images']) > 0
    pdf_received = session.get('pdf_file_id') is not None
    bot.send_message(cid, "Done!", reply_markup=main_menu(images_present=images_present, pdf_received=pdf_received))

bot.infinity_polling()
