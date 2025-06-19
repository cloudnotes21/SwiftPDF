import os
import fitz  # PyMuPDF
import telebot
from telebot import types

API_TOKEN = os.getenv("API_TOKEN")  # Set in Railway env
ADMIN_ID = int(os.getenv("ADMIN_ID"))  # Set in Railway env

bot = telebot.TeleBot(API_TOKEN)

# Session storage for users
user_sessions = {}

# Create folder if not exists
if not os.path.exists("downloads"):
    os.makedirs("downloads")

def extract_images_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    image_paths = []
    for page_index in range(len(doc)):
        for img_index, img in enumerate(doc.get_page_images(page_index)):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            ext = base_image["ext"]
            filename = f"downloads/page{page_index+1}_img{img_index+1}.{ext}"
            with open(filename, "wb") as f:
                f.write(image_bytes)
            image_paths.append(filename)
    return image_paths

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(message.chat.id, "👋 Welcome! Send a PDF file to extract images from it.")

@bot.message_handler(content_types=['document'])
def handle_document(message):
    if message.document.mime_type == 'application/pdf':
        user_id = message.from_user.id
        file_id = message.document.file_id
        user_sessions[user_id] = {'pdf_file_id': file_id}

        # Show menu with "Extract Images" option
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add("🖼 Extract Images")
        bot.send_message(user_id, "📄 PDF received. What would you like to do?", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "❗️Please send a valid PDF file.")

@bot.message_handler(func=lambda m: m.text == "🖼 Extract Images")
def extract_command(message):
    user_id = message.from_user.id
    session = user_sessions.get(user_id)

    if not session or 'pdf_file_id' not in session:
        bot.send_message(user_id, "❗️Please send a PDF file first.")
        return

    msg = bot.send_message(user_id, "⏬ Downloading PDF...")
    file_info = bot.get_file(session['pdf_file_id'])
    file_data = bot.download_file(file_info.file_path)

    pdf_path = f"downloads/{user_id}_temp.pdf"
    with open(pdf_path, 'wb') as f:
        f.write(file_data)

    bot.edit_message_text("🔍 Extracting images...", chat_id=message.chat.id, message_id=msg.message_id)
    images = extract_images_from_pdf(pdf_path)

    if not images:
        bot.send_message(user_id, "⚠️ No images found in this PDF.")
    else:
        for img_path in images:
            with open(img_path, 'rb') as img_file:
                bot.send_photo(user_id, img_file)
        bot.send_message(user_id, f"✅ Done! Extracted {len(images)} image(s).")

    # Clean up
    os.remove(pdf_path)
    for img in images:
        os.remove(img)

@bot.message_handler(func=lambda m: True)
def fallback(message):
    bot.send_message(message.chat.id, "❗️Send a PDF file to begin.")

print("🤖 Bot is running...")
bot.infinity_polling()
