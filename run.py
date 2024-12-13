from pathlib import Path
from dotenv import load_dotenv
import logging


import os
import sys
from telegram import Update
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler, 
    MessageHandler,
    filters
)

from db_manager import DatabaseManager
from message_formatter import MessageFormatter
from handlers.menu_handler import MenuHandler
from bot_commands import BotCommands
from analyzer_queue import AnalyzerQueue
from handlers import HandlerManager
from nowpayments_handler import NOWPaymentsHandler  # Add this import
from session_manager import SessionManager
from file_cleaner import FileCleaner

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('token_analyzer.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

class CustomFormatter(logging.Formatter):
    def __init__(self):
        super().__init__('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    def formatException(self, exc_info):
        result = super().formatException(exc_info)
        return str(result).encode('utf-8', 'ignore').decode('utf-8')

    def format(self, record):
        record.msg = str(record.msg).encode('utf-8', 'ignore').decode('utf-8')
        return super().format(record)

formatter = CustomFormatter()
for handler in logging.root.handlers:
    handler.setFormatter(formatter)

logger = logging.getLogger('TokenAnalyzer')

class TokenAnalyzerBot:
    def __init__(self):
        self.db_manager = None
        self.menu_handler = None
        self.message_formatter = None
        self.analyzer_queue = None
        self.bot_commands = None
        self.handler_manager = None
        self.session_manager = None
        self.file_cleaner = None  # Add this
        
        # Load environment variables
        env_path = Path('.') / '.env'
        load_dotenv(dotenv_path=env_path)
        
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not self.token:
            raise ValueError("No telegram bot token found!")

    def init_components(self):
        """Initialize all components"""
        logger.info("Initializing components...")
        try:
            # Initialize file cleaner first
            self.file_cleaner = FileCleaner(
                directories=['.', 'test'],
                file_types=['.csv', '.txt'],
                max_age_minutes=5
            )
            self.file_cleaner.start()
            
            self.session_manager = SessionManager()
            self.db_manager = DatabaseManager()
            self.analyzer_queue = AnalyzerQueue(self.db_manager)
            self.message_formatter = MessageFormatter()
            self.menu_handler = MenuHandler(
                db_manager=self.db_manager,
                analyzer_queue=self.analyzer_queue,
                session_manager=self.session_manager
            )

            self.payment_handler = NOWPaymentsHandler(os.getenv('NOWPAYMENTS_API_KEY'), self.db_manager)

            
            # Initialize bot commands
            self.bot_commands = BotCommands(
                self.db_manager,
                self.analyzer_queue,
                self.message_formatter,
                self.menu_handler,
                self.session_manager  # Add this

            )
            self.bot_commands.set_payment_handler(self.payment_handler)

            self.handler_manager = HandlerManager(
                db_manager=self.db_manager,
                analyzer_queue=self.analyzer_queue,
                menu_handler=self.menu_handler,
                message_formatter=self.message_formatter,
                bot_commands=self.bot_commands,
                session_manager=self.session_manager
                
            )
            
            logger.info("Components initialized successfully")
        except Exception as e:
            logger.error(f"Init error: {str(e)}")
            raise

    def stop(self):
        """Cleanup method to stop all components"""
        try:
            if self.file_cleaner:
                self.file_cleaner.stop()
                logger.info("File cleaner stopped")
        except Exception as e:
            logger.error(f"Error stopping components: {str(e)}")

    def run(self):
        """Initialize and start the bot"""
        try:
            self.init_components()
            
            # Create application
            application = Application.builder().token(self.token).build()
            self.analyzer_queue.set_application(application)
            
            # Add handlers
            application.add_handler(CommandHandler("start", self.bot_commands.start))
            application.add_handler(CommandHandler("analyze", self.bot_commands.analyze))
            application.add_handler(CommandHandler("queue", self.bot_commands.queue_command))
            application.add_handler(CallbackQueryHandler(self.handler_manager.handle_callback))
            application.add_handler(CommandHandler("buy", self.bot_commands.handle_buy_credits))
            application.add_handler(
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    self.handler_manager.text_handler.handle_text_message
                )
            )
            application.add_error_handler(self.handler_manager.error_handler.handle_error)
            
            logger.info("Bot started")
            application.run_polling(allowed_updates=Update.ALL_TYPES)
            
        except Exception as e:
            logger.error(f"Fatal error: {str(e)}")
            raise
        finally:
            self.stop()  # Ensure cleanup happens

def main():
    bot = TokenAnalyzerBot()
    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot stopped due to error: {str(e)}")
    finally:
        bot.stop()

if __name__ == '__main__':
    main()