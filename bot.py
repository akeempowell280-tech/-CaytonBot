import os
import sys
import logging
import asyncio
from pathlib import Path
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, FSInputFile, 
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from utils.converter import ImageConverter

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    logging.error("❌ BOT_TOKEN is not set")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)

BOT_NAME = "CaytonBot"
BOT_VERSION = "1.0.0"
SUPPORTED_FORMATS = ["PNG", "JPG", "JPEG", "WEBP", "BMP", "ICO", "GIF", "TIFF"]

class ConversionStates(StatesGroup):
    waiting_for_image = State()
    selecting_target_format = State()

def get_format_keyboard() -> InlineKeyboardMarkup:
    keyboard = []
    row = []
    for i, fmt in enumerate(SUPPORTED_FORMATS):
        row.append(InlineKeyboardButton(text=fmt, callback_data=f"format_{fmt}"))
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(text="❌ Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Convert Image", callback_data="start_convert"),
                InlineKeyboardButton(text="📋 Formats", callback_data="show_formats")
            ],
            [
                InlineKeyboardButton(text="ℹ️ About", callback_data="show_about"),
                InlineKeyboardButton(text="❓ Help", callback_data="show_help")
            ]
        ]
    )

@dp.message(Command("start"))
async def start_command(message: Message):
    logger.info(f"✅ Start from {message.from_user.id}")
    await message.answer(
        f"👋 Hello {message.from_user.first_name}!\n\n"
        "Welcome to CaytonBot - Image Converter!\n\n"
        "Send /convert to start converting images.",
        reply_markup=get_main_menu_keyboard()
    )

@dp.message(Command("convert"))
async def convert_command(message: Message, state: FSMContext):
    await state.set_state(ConversionStates.selecting_target_format)
    await message.answer(
        "Select target format:",
        reply_markup=get_format_keyboard()
    )

@dp.message(Command("formats"))
async def formats_command(message: Message):
    text = "📋 Supported Formats:\n\n"
    for fmt in SUPPORTED_FORMATS:
        text += f"• {fmt}\n"
    await message.answer(text)

@dp.message(Command("about"))
async def about_command(message: Message):
    await message.answer(
        f"🤖 {BOT_NAME}\n"
        f"Version: {BOT_VERSION}\n"
        "Built with Aiogram 3 & Pillow\n"
        "Status: ✅ Online"
    )

@dp.message(Command("help"))
async def help_command(message: Message):
    await message.answer(
        "Commands:\n"
        "/start - Start bot\n"
        "/convert - Convert image\n"
        "/formats - Show formats\n"
        "/about - Bot info\n"
        "/help - This message"
    )

@dp.callback_query(lambda c: c.data == "start_convert")
async def start_convert_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await convert_command(callback.message, state)
    await callback.message.delete()

@dp.callback_query(lambda c: c.data == "show_formats")
async def show_formats_callback(callback: CallbackQuery):
    await callback.answer()
    await formats_command(callback.message)

@dp.callback_query(lambda c: c.data == "show_about")
async def show_about_callback(callback: CallbackQuery):
    await callback.answer()
    await about_command(callback.message)

@dp.callback_query(lambda c: c.data == "show_help")
async def show_help_callback(callback: CallbackQuery):
    await callback.answer()
    await help_command(callback.message)

@dp.callback_query(lambda c: c.data.startswith("format_"))
async def format_selection_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    target_format = callback.data.split("_")[1]
    await state.update_data(target_format=target_format)
    await state.set_state(ConversionStates.waiting_for_image)
    await callback.message.answer(
        f"✅ Format: {target_format}\n\nSend me the image to convert.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="❌ Cancel", callback_data="cancel")
            ]]
        )
    )
    await callback.message.delete()

@dp.callback_query(lambda c: c.data == "cancel")
async def cancel_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.answer("❌ Cancelled. Use /convert to start again.")

@dp.message(ConversionStates.waiting_for_image)
async def handle_image(message: Message, state: FSMContext):
    try:
        if not message.photo and not message.document:
            await message.answer("⚠️ Please send an image file.")
            return
        
        if message.photo:
            file = message.photo[-1]
            file_name = f"image_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        else:
            file = message.document
            if file.mime_type and not file.mime_type.startswith("image/"):
                await message.answer("⚠️ Please send an image file.")
                return
            file_name = file.file_name or f"image_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        
        processing_msg = await message.answer("⏳ Processing...")
        
        file_path = TEMP_DIR / file_name
        await bot.download(file, file_path)
        
        state_data = await state.get_data()
        target_format = state_data.get("target_format", "PNG")
        
        converter = ImageConverter()
        output_file = TEMP_DIR / f"converted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{target_format.lower()}"
        
        success, result = await converter.convert(
            input_path=file_path,
            output_path=output_file,
            target_format=target_format.lower()
        )
        
        if not success:
            await processing_msg.edit_text(f"❌ {result}")
            await state.clear()
            return
        
        await processing_msg.delete()
        
        original_size = file_path.stat().st_size / 1024
        new_size = output_file.stat().st_size / 1024
        
        document = FSInputFile(output_file, filename=output_file.name)
        await message.answer_document(
            document,
            caption=f"✅ Converted to {target_format}\n📊 {original_size:.1f}KB → {new_size:.1f}KB"
        )
        
        await message.answer(
            "🔄 Convert another?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(text="✅ Yes", callback_data="start_convert"),
                    InlineKeyboardButton(text="❌ No", callback_data="cancel")
                ]]
            )
        )
        
        try:
            file_path.unlink()
            output_file.unlink()
        except:
            pass
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await message.answer(f"❌ Error: {str(e)}")
        await state.clear()

@dp.message()
async def handle_unknown(message: Message):
    await message.answer("Use /start or /convert")

async def main():
    logger.info(f"🚀 Starting {BOT_NAME}...")
    logger.info(f"🐍 Python: {sys.version}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
