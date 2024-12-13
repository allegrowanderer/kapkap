# handlers/error_handlers.py
import logging
import traceback
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import (
    TelegramError,
    Forbidden,
    BadRequest,
    TimedOut,
    NetworkError,
    RetryAfter
)
import asyncio

class ErrorHandler:
    def __init__(self, analyzer_queue):
        self.analyzer_queue = analyzer_queue
        self.logger = logging.getLogger('TokenAnalyzer')
        self.max_retries = 3
        self.base_delay = 1  # Base delay in seconds

    async def handle_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors that occur during bot operation"""
        try:
            if isinstance(context.error, RetryAfter):
                await self._handle_retry_after(update, context)
                return

            if isinstance(context.error, NetworkError):
                await self._handle_network_error(update, context)
                return

            if update and update.effective_chat:
                chat_id = update.effective_chat.id
                error_message = self._get_user_friendly_error_message(context.error)
                
                # Try to send error message with retries
                for attempt in range(self.max_retries):
                    try:
                        await self.analyzer_queue.send_message(
                            chat_id=chat_id,
                            text=error_message
                        )
                        break
                    except (NetworkError, TimedOut) as e:
                        if attempt == self.max_retries - 1:
                            self.logger.error(f"Failed to send error message after {self.max_retries} attempts")
                        else:
                            await asyncio.sleep(self.base_delay * (attempt + 1))
            
            self._log_error(update, context)
            
        except Exception as e:
            self.logger.error(f"Error in error handler: {str(e)}")

    async def _handle_retry_after(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle RetryAfter errors"""
        retry_after = context.error.retry_after
        self.logger.warning(f'RetryAfter: {retry_after}')
        await asyncio.sleep(retry_after)
        
        if update and update.effective_chat:
            await self.analyzer_queue.send_message(
                chat_id=update.effective_chat.id,
                text="⚠️ Rate limit reached. Please wait a moment and try again."
            )

    async def _handle_network_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle NetworkError with retries"""
        for attempt in range(self.max_retries):
            try:
                if update and update.effective_chat:
                    await self.analyzer_queue.send_message(
                        chat_id=update.effective_chat.id,
                        text="⚠️ Network error occurred. Retrying..."
                    )
                    
                # Wait with exponential backoff
                await asyncio.sleep(self.base_delay * (2 ** attempt))
                return
                
            except Exception as e:
                if attempt == self.max_retries - 1:
                    self.logger.error(f"Network error persists after {self.max_retries} retries: {str(e)}")
                    if update and update.effective_chat:
                        try:
                            await self.analyzer_queue.send_message(
                                chat_id=update.effective_chat.id,
                                text="❌ Network error. Please try again later."
                            )
                        except:
                            pass

    def _get_user_friendly_error_message(self, error: Exception) -> str:
        """Convert exception to user-friendly message"""
        if isinstance(error, Forbidden):
            return "❌ Bot lacks necessary permissions. Please check bot permissions."
        
        elif isinstance(error, BadRequest):
            return "❌ Invalid request. Please try again or use /start."
        
        elif isinstance(error, TimedOut):
            return "⚠️ Request timed out. Please try again."
        
        elif isinstance(error, NetworkError):
            return "⚠️ Network error occurred. Please try again later."
        
        elif isinstance(error, TelegramError):
            return "❌ Telegram error occurred. Please try again later."
        
        return "❌ An error occurred. Please try again or use /start."

    def _log_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Log error details for debugging"""
        self.logger.error(
            "Exception while handling an update:",
            exc_info=context.error
        )

        if update:
            self.logger.error(
                f"Update {update} caused error: {context.error}\n" +
                f"Traceback:\n{traceback.format_exc()}"
            )
        
        if context.chat_data:
            self.logger.error(f"Chat data: {str(context.chat_data)}")
            
        if context.user_data:
            self.logger.error(f"User data: {str(context.user_data)}")

    async def handle_timeout_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle timeout errors specifically"""
        for attempt in range(self.max_retries):
            try:
                if update and update.effective_chat:
                    await self.analyzer_queue.send_message(
                        chat_id=update.effective_chat.id,
                        text="⚠️ Analysis is taking longer than expected. Retrying..."
                    )
                return
            except Exception as e:
                if attempt == self.max_retries - 1:
                    self.logger.error(f"Timeout persists after {self.max_retries} retries: {str(e)}")

    async def handle_rate_limit_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle rate limiting errors"""
        if update and update.effective_chat:
            await self.analyzer_queue.send_message(
                chat_id=update.effective_chat.id,
                text="⚠️ Too many requests. Please wait a few minutes and try again."
            )
        self.logger.warning(f"Rate limit hit: {context.error}")