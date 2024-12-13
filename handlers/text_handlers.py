# text_handlers.py

from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import NetworkError, TimedOut, BadRequest
import logging
import time
import asyncio
from typing import Dict, Set, Optional
import re
from web3.exceptions import ContractLogicError
from datetime import datetime
from enum import Enum

class AddressValidationError(Exception):
   pass

class UserState(Enum):
   MAIN_MENU = "main_menu" 
   AWAITING_ADDRESS = "awaiting_address"
   SELECTING_ANALYSIS = "selecting_analysis"
   ANALYZING = "analyzing"
   VIEWING_RESULTS = "viewing_results"

class TextHandler:
    def __init__(self, db_manager, menu_handler, analyzer_queue, bot_commands, session_manager):
        self.db_manager = db_manager
        self.menu_handler = menu_handler
        self.analyzer_queue = analyzer_queue
        self.bot_commands = bot_commands
        self.session_manager = session_manager
        self.logger = logging.getLogger('TokenAnalyzer')
        self.max_retries = 3
        self.base_retry_delay = 1
        self.rate_limit_cooldown = 30
        self.restricted_addresses: Set[str] = {
            "0x35762b6E2d33B906f275103Aaf9Da814A1ff42b6",
        }
        self.validation_cache: Dict[str, Dict] = {}
        self.cache_ttl = 3600

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.message.text:
            return

        user_id = update.effective_user.id
        text = update.message.text.strip()
        session = self.session_manager.get_session(user_id)

        # Add debug logging
        self.logger.info(f"Received text message: {text} from user {user_id}")
        self.logger.info(f"Current session state: {session.state}")

        try:
            # Check if waiting for address
            if session.state != UserState.AWAITING_ADDRESS:
                self.logger.info(f"Not awaiting address. Current state: {session.state}")
                return

            # Validate address format
            if not text.startswith('0x'):
                await update.message.reply_text(
                    "❌ Please provide a valid token address starting with '0x'",
                    parse_mode='Markdown'
                )
                return

            await self._process_address(update, context, text, session)

        except Exception as e:
            self.logger.error(f"Error handling text message: {str(e)}", exc_info=True)
            await update.message.reply_text(
                "❌ An error occurred processing your request. Please try again."
            )

    async def _process_address(self, update: Update, context: ContextTypes.DEFAULT_TYPE, address: str, session) -> None:
        user_id = update.effective_user.id

        # Explicitly check if state is awaiting address
        if session.state != UserState.AWAITING_ADDRESS:
            return

        # Get analysis type directly from session
        analysis_type = session.temp_data.get('analysis_type')
        
        # If no analysis type found, check pending menu selection
        if not analysis_type:
            analysis_type = 'deep' if session.temp_data.get('pending_analysis') == 'deep' else 'quick'
            session.temp_data['analysis_type'] = analysis_type

        # Set correct parameters based on analysis type
        credits_needed = 5 if analysis_type == 'deep' else 1
        holders = 50 if analysis_type == 'deep' else 10

        try:
            # Validate address format and checksum
            
            validation_result = await self._validate_address(address)
            if not validation_result['valid']:
                raise AddressValidationError(validation_result['message'])

            checksummed_address = validation_result['address']

            # Check restricted addresses
            if self._is_restricted_address(checksummed_address):
                raise AddressValidationError(
                    '''They asked the tree, "What do you fear the most?" The tree replied, "The axe, because its handle is made from my own wood."\n'''
                    "Please provide a different token contract address."
                )

            # Show progress while verifying contract
            progress_msg = await update.message.reply_text("🔍 Verifying contract...")
            try:
                if not await self._verify_contract(checksummed_address):
                    await progress_msg.edit_text(
                        "❌ This address is not a contract.\n"
                        "Please provide a valid token contract address."
                    )
                    return
            finally:
                await progress_msg.delete()

            # Check user has enough credits
            user_data = self.db_manager.get_user(user_id)
            if not user_data or user_data['credits'] < credits_needed:
                await update.message.reply_text(
                    f"❌ Insufficient credits. Need {credits_needed} credits.\n"
                    f"Your balance: {user_data['credits'] if user_data else 0}\n\n"
                    f"Use /buy to purchase more credits."
                )
                return

            # Store address and update state
            self.session_manager.store_temp_data(user_id, 'current_address', checksummed_address)
            self.session_manager.store_temp_data(user_id, 'analysis_type', analysis_type)
            self.session_manager.update_state(user_id, UserState.SELECTING_ANALYSIS)


            # Send confirmation message
            confirmation_text = (
                f"🔍 *Token Address Verified*\n\n"
                f"Address: `{checksummed_address}`\n"
                f"Analysis: {analysis_type.title()}\n" 
                f"Holders: {holders}\n"
                f"Ready to start analysis?"
            )

            await update.message.reply_text(
                confirmation_text,
                reply_markup=self.menu_handler.get_analysis_options(
                    checksummed_address,
                    analysis_type
                ),
                parse_mode='Markdown'
            )

        except AddressValidationError as e:
            await update.message.reply_text(str(e))
            self.session_manager.update_state(user_id, UserState.AWAITING_ADDRESS)

        except Exception as e:
            await self._handle_error(update, e)
            self.session_manager.update_state(user_id, UserState.MAIN_MENU)

    async def _validate_address(self, address: str) -> Dict:
        """Validate ethereum address format and checksum"""
        try:
            # Check basic format
            if not re.match(r'^0x[a-fA-F0-9]{40}$', address):
                return {
                    'valid': False,
                    'message': (
                        "❌ Invalid address format.\n"
                        "Address must be 42 characters long and contain only hex characters."
                    )
                }

            # Convert to checksum address
            checksummed_address = self.bot_commands.w3.to_checksum_address(address)

            return {
                'valid': True,
                'address': checksummed_address,
                'message': "Address validated successfully"
            }

        except ValueError:
            return {
                'valid': False,
                'message': "❌ Invalid address checksum.\nPlease verify the address and try again."
            }

    async def _verify_contract(self, address: str) -> bool:
        """Verify if address is a contract with retry logic"""
        for attempt in range(self.max_retries):
            try:
                code = await self._get_code_with_retry(address)
                return len(code) > 0
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(self.base_retry_delay * (attempt + 1))
        return False

    async def _get_code_with_retry(self, address: str) -> bytes:
        """Get contract code with retry logic"""
        for attempt in range(self.max_retries):
            try:
                return self.bot_commands.w3.eth.get_code(address)
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(self.base_retry_delay * (attempt + 1))
        return bytes()

    def _is_restricted_address(self, address: str) -> bool:
        """Check if address is in restricted list"""
        return address.lower() in {addr.lower() for addr in self.restricted_addresses}

    async def _check_user_credits(self, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> Dict:
        """Check if user has sufficient credits"""
        analysis_type = context.user_data.get('analysis_type', 'quick')
        credits_needed = 5 if analysis_type == 'deep' else 1
        holders = 50 if analysis_type == 'deep' else 10

        user_data = self.db_manager.get_user(user_id)
        if not user_data or user_data['credits'] < credits_needed:
            return {
                'success': False,
                'message': (
                    f"❌ Insufficient credits. Need {credits_needed} credits.\n"
                    f"Your balance: {user_data['credits'] if user_data else 0}\n\n"
                    f"Use /buy to purchase more credits."
                )
            }

        return {
            'success': True,
            'analysis_type': analysis_type,
            'credits_needed': credits_needed,
            'holders': holders
        }

    async def _send_analysis_confirmation(
        self,
        update: Update,
        address: str,
        analysis_type: str,
        credits_needed: int
    ) -> None:
        """Send analysis confirmation message"""
        holders = 50 if analysis_type == 'deep' else 10
        
        confirmation_text = (
            f"🔍 *Token Address Verified*\n\n"
            f"Address: `{address}`\n"
            f"Analysis: {analysis_type.title()}\n"
            f"Holders: {holders}\n"
            f"Ready to start analysis?"
        )
        
        await update.message.reply_text(
            confirmation_text,
            reply_markup=self.menu_handler.get_analysis_options(address, analysis_type),
            parse_mode='Markdown'
        )

    async def _handle_error(self, update: Update, error: Exception) -> None:
        """Handle errors during text processing"""
        error_message = "❌ An error occurred. Please try again."
        
        if isinstance(error, (NetworkError, TimedOut)):
            error_message = "❌ Network error occurred. Please try again in a few moments."
        elif isinstance(error, BadRequest):
            error_message = "❌ Invalid request. Please check your input and try again."
        
        self.logger.error(f"Error processing message: {str(error)}")
        
        try:
            await update.message.reply_text(error_message)
        except Exception as e:
            self.logger.error(f"Error sending error message: {str(e)}")

    def _get_remaining_cooldown(self, user_id: int) -> int:
        """Calculate remaining cooldown time"""
        session = self.session_manager.get_session(user_id)
        last_check = session.rate_limits.get('address_check', 0)
        elapsed = time.time() - last_check
        return max(0, int(self.rate_limit_cooldown - elapsed))

    def _cleanup_validation_cache(self) -> None:
        """Clean up expired validation cache entries"""
        current_time = time.time()
        expired = [
            addr for addr, data in self.validation_cache.items()
            if current_time - data['timestamp'] > self.cache_ttl
        ]
        for addr in expired:
            del self.validation_cache[addr]