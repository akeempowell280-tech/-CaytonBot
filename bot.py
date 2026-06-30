import os
import sys
import logging
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Tuple, Optional

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
from PIL import Image

# ============ CONFIGURATION ============

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DEBUG_MODE = os.getenv("DEBUG_MODE", "False").lower() == "true"

if not BOT_TOKEN:
    print("❌ BOT_TOKEN is not set in environment variables")
    sys.exit(1)

# ============ LOGGING ============

log_level = logging.DEBUG if DEBUG_MODE else logging.INFO
logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ============ BOT INITIALIZATION ============

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ============ CONSTANTS ============

BOT_VERSION = "1.0.0"
BOT_NAME = "CaytonBot"
TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)

SUPPORTED_FORMATS = [
    "PNG", "JPG", "JPEG", "WEBP", 
    "BMP", "ICO", "GIF", "TIFF"
]

# ============ IMAGE CONVERTER CLASS ============

class ImageConverter:
    """Handles image conversion operations"""
    
    def __init__(self, max_size_mb: int = 20):
        self.max_size_mb = max_size_mb
    
    async def convert(
        self,
        input_path: Path,
        output_path: Path,
        target_format: str,
        quality: int = 90,
        resize: Optional[Tuple[int, int]] = None
    ) -> Tuple[bool, str]:
        """Convert an image to the specified format"""
        try:
            # Validate input file
            if not input_path.exists():
                return False, "Input file not found"
            
            # Check file size
            file_size_mb = input_path.stat().st_size / (1024 * 1024)
            if file_size_mb > self.max_size_mb:
                return False, f"File too large ({file_size_mb:.1f}MB). Max: {self.max_size_mb}MB"
            
            # Open image
            try:
                img = Image.open(input_path)
            except Exception as e:
                return False, f"Failed to open image: {str(e)}"
            
            # Resize if requested
            if resize:
                img = img.resize(resize, Image.Resampling.LANCZOS)
            
            # Handle transparency for JPEG
            if target_format.lower() in ["jpg", "jpeg"] and img.mode in ["RGBA", "P", "LA"]:
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "RGBA":
                    mask = img.split()[3] if len(img.split()) > 3 else None
                    background.paste(img, mask=mask)
                else:
                    background.paste(img)
                img = background
            
            # Convert to RGB for BMP
            if target_format.lower() == "bmp" and img.mode in ["RGBA", "LA"]:
                img = img.convert("RGB")
            
            # Handle ICO format
            if target_format.lower() == "ico":
                if img.size[0] > 256 or img.size[1] > 256:
                    img = img.resize((256, 256), Image.Resampling.LANCZOS)
            
            # Save with proper parameters
            save_kwargs = {}
            format_upper = target_format.upper()
            
            if target_format.lower() in ["jpg", "jpeg"]:
                save_kwargs["quality"] = quality
                save_kwargs["optimize"] = True
            elif target_format.lower() == "webp":
                save_kwargs["quality"] = quality
                save_kwargs["method"] = 6
            elif target_format.lower() == "png":
                save_kwargs["optimize"] = True
                save_kwargs["compress_level"] = 6
            
            # Save image
            img.save(output_path, format=format_upper, **save_kwargs)
            
            # Validate output
            if not output_path.exists() or output_path.stat().st_size == 0:
                return False, "Conversion failed - output file is empty"
            
            return True, f"Successfully converted to {format_upper}"
            
        except Exception as e:
            logger.error(f"Conversion error: {e}")
            return False, f"Conversion error: {str(e)}"

# ============ STATES ============

class ConversionStates(StatesGroup):
    waiting_for_image = State()
    selecting_target_format = State()

# ============ KEYBOARDS ============

def get_format_keyboard() -> InlineKeyboardMarkup:
    """Generate keyboard with all format options"""
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
    """Generate main menu keyboard"""
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

# ============ COMMAND HANDLERS ============

@dp.message(Command("start"))
async def start_command(message: Message):
    """Handle /start command"""
    logger.info(f"✅ Start command received from {message.from_user.id}")
    
    welcome_text = (
        f"👋 **Hello {message.from_user.first_name}!**\n\n"
        "Welcome to **CaytonBot** - your professional image conversion assistant!\n\n"
        "📸 **Features:**\n"
        "• Convert between 8 image formats\n"
        "• High-quality output\n"
        "• Fast processing\n"
        "• User-friendly interface\n\n"
        "🔧 **How to use:**\n"
        "1. Send /convert or click the button below\n"
        "2. Select your target format\n"
        "3. Upload the image\n"
        "4. Download your converted image!\n\n"
        "📊 **Commands:**\n"
        "/start - Show this menu\n"
        "/convert - Start conversion\n"
        "/formats - Show supported formats\n"
        "/about - Bot information\n"
        "/help - Get help"
    )
    
    await message.answer(
        welcome_text, 
        reply_markup=get_main_menu_keyboard(), 
        parse_mode="Markdown"
    )

@dp.message(Command("convert"))
async def convert_command(message: Message, state: FSMContext):
    """Handle /convert command"""
    logger.info(f"🔄 Convert command received from {message.from_user.id}")
    await state.set_state(ConversionStates.selecting_target_format)
    
    await message.answer(
        "🔄 **Start Image Conversion**\n\n"
        "Please select the **target format** you want to convert to:",
        reply_markup=get_format_keyboard(),
        parse_mode="Markdown"
    )

@dp.message(Command("formats"))
async def formats_command(message: Message):
    """Handle /formats command"""
    formats_text = "📋 **Supported Image Formats:**\n\n"
    for fmt in SUPPORTED_FORMATS:
        formats_text += f"• `{fmt}`\n"
    
    await message.answer(formats_text, parse_mode="Markdown")

@dp.message(Command("about"))
async def about_command(message: Message):
    """Handle /about command"""
    about_text = (
        f"🤖 **{BOT_NAME}**\n\n"
        f"📌 Version: `{BOT_VERSION}`\n"
        "⚡ Built with: `Aiogram 3` & `Pillow`\n"
        "📅 Status: ✅ **Online**\n\n"
        "🔹 **Features:**\n"
        "• Convert between 8 image formats\n"
        "• High-quality output\n"
        "• Fast processing\n"
        "• User-friendly interface\n\n"
        f"💡 **Created for:** @{BOT_NAME}"
    )
    await message.answer(about_text, parse_mode="Markdown")

@dp.message(Command("help"))
async def help_command(message: Message):
    """Handle /help command"""
    help_text = (
        "🆘 **Help & Support**\n\n"
        "📖 **Basic Usage:**\n"
        "1. Send /convert\n"
        "2. Choose target format\n"
        "3. Upload image\n"
        "4. Wait for conversion\n\n"
        "⚡ **Tips:**\n"
        "• You can convert multiple images\n"
        "• Cancel with ❌ button\n"
        "• Large images may take a few seconds\n"
        "• Maximum file size: 20MB\n\n"
        "❓ **Need more help?**\n"
        f"Contact @{BOT_NAME} support."
    )
    await message.answer(help_text, parse_mode="Markdown")

# ============ CALLBACK QUERY HANDLERS ============

@dp.callback_query(lambda c: c.data == "start_convert")
async def start_convert_callback(callback: CallbackQuery, state: FSMContext):
    """Handle start conversion from menu"""
    await callback.answer()
    await convert_command(callback.message, state)
    await callback.message.delete()

@dp.callback_query(lambda c: c.data == "show_formats")
async def show_formats_callback(callback: CallbackQuery):
    """Handle show formats from menu"""
    await callback.answer()
    await formats_command(callback.message)

@dp.callback_query(lambda c: c.data == "show_about")
async def show_about_callback(callback: CallbackQuery):
    """Handle show about from menu"""
    await callback.answer()
    await about_command(callback.message)

@dp.callback_query(lambda c: c.data == "show_help")
async def show_help_callback(callback: CallbackQuery):
    """Handle show help from menu"""
    await callback.answer()
    await help_command(callback.message)

@dp.callback_query(lambda c: c.data.startswith("format_"))
async def format_selection_callback(callback: CallbackQuery, state: FSMContext):
    """Handle format selection"""
    await callback.answer()
    
    target_format = callback.data.split("_")[1]
    await state.update_data(target_format=target_format)
    await state.set_state(ConversionStates.waiting_for_image)
    
    await callback.message.answer(
        f"✅ **Selected format:** `{target_format}`\n\n"
        "📤 **Now send me the image you want to convert.**\n"
        "You can send it as a photo or file.\n\n"
        "⚠️ Maximum file size: 20MB",
        parse_mode="Markdown"
    )
    await callback.message.delete()

@dp.callback_query(lambda c: c.data == "cancel")
async def cancel_callback(callback: CallbackQuery, state: FSMContext):
    """Handle cancel callback"""
    await callback.answer()
    await state.clear()
    await callback.message.answer(
        "❌ **Operation cancelled.**\n\n"
        "Use /convert to start again.",
        parse_mode="Markdown"
    )
    await callback.message.delete()

# ============ MESSAGE HANDLERS ============

@dp.message(ConversionStates.waiting_for_image)
async def handle_image(message: Message, state: FSMContext):
    """Handle image upload for conversion"""
    try:
        if not message.photo and not message.document:
            await message.answer(
                "⚠️ **Please send an image file.**\n\n"
                "You can send it as a photo or document.",
                parse_mode="Markdown"
            )
            return
        
        if message.photo:
            file = message.photo[-1]
            file_extension = "jpg"
            file_name = f"image_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        else:
            file = message.document
            if file.mime_type and not file.mime_type.startswith("image/"):
                await message.answer(
                    "⚠️ **Please send an image file.**\n\n"
                    f"Received: `{file.mime_type}`",
                    parse_mode="Markdown"
                )
                return
            
            file_extension = file.file_name.split('.')[-1].lower() if file.file_name else "jpg"
            file_name = file.file_name or f"image_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{file_extension}"
        
        processing_msg = await message.answer("⏳ **Processing your image...**", parse_mode="Markdown")
        
        file_path = TEMP_DIR / file_name
        await bot.download(file, file_path)
        
        state_data = await state.get_data()
        target_format = state_data.get("target_format", "PNG")
        
        converter = ImageConverter(max_size_mb=20)
        
        source_format = file_extension.upper()
        if source_format == "JPG":
            source_format = "JPEG"
        
        output_format = target_format.lower()
        output_file = TEMP_DIR / f"converted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{output_format}"
        
        success, result = await converter.convert(
            input_path=file_path,
            output_path=output_file,
            target_format=output_format,
            quality=90
        )
        
        if not success:
            await processing_msg.edit_text(f"❌ **Conversion Failed:** {result}", parse_mode="Markdown")
            await state.clear()
            return
        
        await processing_msg.delete()
        
        original_size = file_path.stat().st_size / 1024
        new_size = output_file.stat().st_size / 1024
        
        caption = (
            f"✅ **Conversion Complete!**\n\n"
            f"📄 **Source:** `{source_format}` → **Target:** `{target_format}`\n"
            f"📊 **Size:** `{original_size:.1f}KB` → `{new_size:.1f}KB`\n"
            f"📥 **Download your image below:**"
        )
        
        document = FSInputFile(output_file, filename=output_file.name)
        await message.answer_document(
            document,
            caption=caption,
            parse_mode="Markdown"
        )
        
        await message.answer(
            "🎯 **Convert another image?**",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Convert Another", callback_data="start_convert")],
                    [InlineKeyboardButton(text="🏠 Main Menu", callback_data="start_convert")]
                ]
            ),
            parse_mode="Markdown"
        )
        
        try:
            file_path.unlink()
            output_file.unlink()
        except Exception as e:
            logger.warning(f"Failed to delete temp files: {e}")
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error in handle_image: {e}")
        await message.answer(f"❌ **An error occurred:** `{str(e)}`", parse_mode="Markdown")
        await state.clear()

@dp.message()
async def handle_unknown(message: Message):
    """Handle unknown messages"""
    await message.answer(
        "❓ **I don't understand that.**\n\n"
        "Use /help to see available commands or /start to get started.",
        parse_mode="Markdown"
    )

# ============ MAIN ============

async def main():
    """Main entry point"""
    logger.info(f"🚀 Starting {BOT_NAME}...")
    logger.info(f"📌 Version: {BOT_VERSION}")
    logger.info(f"🐍 Python: {sys.version}")
    logger.info(f"🔧 Debug Mode: {DEBUG_MODE}")
    logger.info(f"📁 Temp Directory: {TEMP_DIR.absolute()}")
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        raise
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
