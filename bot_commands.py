from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import ContextTypes
from web3 import Web3
import logging
import asyncio
from typing import Dict
from queue_status import QueueStatus

class BotCommands:
    def __init__(self, db_manager, analyzer_queue, message_formatter, menu_handler, session_manager):
        self.db = db_manager
        self.analyzer = analyzer_queue
        self.formatter = message_formatter
        self.menu = menu_handler
        self.payment_handler = None
        self.w3 = Web3(Web3.HTTPProvider('https://mainnet.base.org'))
        self.logger = logging.getLogger('TokenAnalyzer')
        self.session_manager = session_manager
    
    def set_payment_handler(self, payment_handler):
        """Set payment handler after initialization"""
        self.payment_handler = payment_handler

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        if not self.db.get_user(user.id):
            self.db.create_user(user.id, user.username)
        
        welcome_text = (
            f"👋 Welcome {user.first_name}!\n\n"
            "Get insights into token holders and developers on the Base Chain with my help.\n\n"
            "🔍 Instant Analysis \n"
            "• Top 10 Token Holders Report\n"
            "• Basic Risk Review\n"
            "• Developer History Check\n"
            "• Transaction history\n\n"
        )
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=self.menu.get_main_menu(),
            parse_mode='Markdown'
        )

    async def analyze(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /analyze command"""
        user = update.effective_user
        user_data = self.db.get_user(user.id)
        
        if not user_data:
            await update.message.reply_text(
                "❌ User not found. Please start the bot again with /start"
            )
            return
        
        if not context.args:
            await update.message.reply_text(
                "Provide the token address to proceed.\n"
                "Follow this format: /analyze <token_address>"
            )
            return
        
        token_address = context.args[0]

        try:
            if not self.w3.is_address(token_address):
                await update.message.reply_text(
                    "❌ Incorrect token address format\n"
                    "Please provide a valid Base Chain token address."
                )
                return

            checksummed_address = self.w3.to_checksum_address(token_address)
            
            # Check if it's a contract
            code = self.w3.eth.get_code(checksummed_address)
            if len(code) == 0:
                await update.message.reply_text(
                    "❌ This address is not a contract.\n"
                    "Please provide a valid token contract address."
                )
                return

            # Show analysis options
            analysis_menu = (
                f"🔍 *Analysis Options for Token*\n"
                f"`{checksummed_address}`\n\n"
                f"*Instant Analysis*\n"
                f"• Analyzes top 10 holders\n"
                f"• Basic risk assessment\n"
                f"• Developer background check\n"
                f"• Transaction history\n\n"
            )

            await update.message.reply_text(
                analysis_menu,
                reply_markup=self.menu.get_analysis_menu(checksummed_address),
                parse_mode='Markdown'
            )

        except Exception as e:
            await update.message.reply_text(
                f"❌ Error processing address: {str(e)}\n"
                "Please try again with a valid token address."
            )

    async def check_credits(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /credits command"""
        user = update.effective_user
        user_data = self.db.get_user(user.id)
        
        if user_data:
            await update.message.reply_text(
                f"💳 *Your Credits*\n\n",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "❌ User not found. Please start the bot again with /start"
            )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = (
            "ℹ️ *Token Analyzer Bot Help*\n\n"
            "*Commands:*\n"
            "• /start - Start the bot and show main menu\n"
            "• /analyze <address> - Analyze a token\n"
            "• /help - Show this help message\n\n"
            "*Analysis Types:*\n"
            "🔍 Instant Analysis (1 credit)\n"
            "• Top 10 holders\n"
            "• Basic risk assessment\n"
            "• Developer check\n\n"
        )
        
        await update.message.reply_text(
            help_text,
            parse_mode='Markdown'
        )

    async def handle_buy_credits(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /buy command"""
        keyboard = [

        ]
        
        await update.message.reply_text(
           
            "if",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    async def handle_buy_callback(self, query: CallbackQuery):
        """Handle buy callback queries with improved error handling and user feedback"""
        try:
            # Rate limit check
            user_id = query.from_user.id
            if not self.session_manager.check_rate_limit(user_id, 'payment_creation', 30):
                await query.answer("Please wait", show_alert=True)
                return

            # Check for pending payment with retry logic
            for attempt in range(3):
                try:
                    pending_payment = await self.db.get_user_pending_payment(user_id)
                    if pending_payment:
                        # Show pending payment details
                        keyboard = [
                            [InlineKeyboardButton("✅ Check Payment Status", 
                            callback_data=f"check_payment_{pending_payment['payment_id']}")],
                            [InlineKeyboardButton("❌ Cancel Payment", 
                            callback_data=f"cancel_payment_{pending_payment['payment_id']}")],
                            [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_main")]
                        ]
                        
                        await query.message.edit_text(
                            f"💳 *Pending  Found*\n\n"
                            f"Amount: `{pending_payment['amount_crypto']} {pending_payment['currency'].upper()}`\n"
                            f"Address: `{pending_payment['pay_address']}`\n\n"
                            f"Credits to receive: {pending_payment['credits']}\n\n"
                            "1️⃣ Send the __EXACT__ amount to the address above\n"
                            "2️⃣ Wait for confirmation (up to 30 minutes)\n"
                            "3️⃣ Click 'Check Payment Status' to verify\n\n"
                            f"⚠️ *Important*: Send only {pending_payment['currency'].upper()} to this address!\n\n"
                            "ℹ️ Complete this payment or wait for it to expire before creating a new one.",
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='Markdown'
                        )
                        return
                    break
                except Exception as e:
                    if attempt == 2:  # Last attempt
                        raise
                    await asyncio.sleep(1)

            # Show processing message
            processing_msg = await query.message.edit_text(
                "💭 Creating ...",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Cancel", callback_data="menu_buy")
                ]])
            )
            
            # Create payment
            package_name = query.data.split('_')[1]
            payment = await self.payment_handler.create_payment(user_id, package_name)
            
            if not payment:
                await processing_msg.edit_text(
                    "❌ Error creating . Please try again later.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Back", callback_data="menu_buy")
                    ]])
                )
                return
            
            if payment.get('error'):
                await processing_msg.edit_text(
                    f"❌ {payment['message']}\n\nPlease try again later.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Back", callback_data="menu_buy")
                    ]])
                )
                return
            
            # Create payment success keyboard
            keyboard = [
                [InlineKeyboardButton("✅ Check Payment Status", 
                                    callback_data=f"check_payment_{payment['payment_id']}")],
                [InlineKeyboardButton("❌ Cancel Payment", 
                                    callback_data=f"cancel_payment_{payment['payment_id']}")],
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_main")]
            ]
            
            # Show payment details using amount_crypto instead of pay_amount
            await processing_msg.edit_text(
                f"💳 *Payment Details*\n\n"
                f"Amount: `{payment['amount_crypto']} {payment['currency'].upper()}`\n"
                f"Address: `{payment['pay_address']}`\n\n"
                f"Credits to receive: {payment['credits']}\n\n"
                "1️⃣ Send the __EXACT__ amount to the address above\n"
                "2️⃣ Wait for confirmation (up to 30 minutes)\n"
                "3️⃣ Click 'Check Payment Status' to verify\n\n"
                f"⚠️ *Important*: Send only {payment['currency'].upper()} to this address!\n\n"
                "ℹ️ Payment will expire in 24 hours if not completed",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
                
        except Exception as e:
            self.logger.error(f"Error in buy callback: {str(e)}")
            await query.message.edit_text(
                "❌ An error occurred while processing your payment request.\n\n"
                "Please try again later or contact support.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back", callback_data="menu_buy")
                ]])
            )

    async def handle_check_payment(self, query: CallbackQuery):
        """Handle payment status check with improved verification"""
        try:
            if not query.data:
                self.logger.error("No callback data in query")
                return

            payment_id = query.data.split('_')[2]
            
            # Show loading state
            loading_msg = await query.message.edit_text(
                "💭 Checking payment status...",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back", callback_data="menu_buy")
                ]])
            )

            # Get payment data with retry
            payment_data = None
            for attempt in range(3):
                try:
                    payment_data = await self.db.get_payment(payment_id)
                    if payment_data:
                        break
                except Exception as e:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(1)
                
            if not payment_data:
                await loading_msg.edit_text(
                    "❌ Payment not found. Please try again or contact support.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Back", callback_data="menu_buy")
                    ]])
                )
                return

            # Check status with payment provider
            status = await self.payment_handler.check_payment_status(payment_id)
            self.logger.info(f"Payment {payment_id} status: {status}")

            if status == 'finished':
                if payment_data['status'] != 'completed':
                    # Update payment status and add credits atomically
                    success = await self._process_successful_payment(payment_data)
                    
                    if success:
                        await loading_msg.edit_text(
                            f"✅ Payment completed!\n\n"
                            f"Added {payment_data['credits']} credits to your account.\n"
                            f"Thank you for your purchase!",
                            reply_markup=InlineKeyboardMarkup([[
                                InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_main")
                            ]])
                        )
                    else:
                        await loading_msg.edit_text(
                            "⚠️ Payment completed but error adding credits.\n"
                            "Please contact support with your payment ID.",
                            reply_markup=InlineKeyboardMarkup([[
                                InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_main")
                            ]])
                        )
                else:
                    await loading_msg.edit_text(
                        "✅ Payment was already processed",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_main")
                        ]])
                    )

            elif status in ['waiting', 'pending']:
                await loading_msg.edit_text(
                    "⏳ Payment is pending confirmation.\n\n"
                    "Please wait a few minutes and check again.\n"
                    f"Amount to send: {payment_data['amount_crypto']} {payment_data['currency'].upper()}\n"
                    f"Address: `{payment_data['pay_address']}`",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔄 Check Again", callback_data=f"check_payment_{payment_id}"),
                        InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_payment_{payment_id}")
                    ]]),
                    parse_mode='Markdown'
                )
                
            elif status == 'failed':
                await self.db.update_payment_status(payment_id, 'failed')
                await loading_msg.edit_text(
                    "❌ Payment failed.\n\n"
                    "Please try again or contact support.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Back to Packages", callback_data="menu_buy")
                    ]])
                )
                
            elif status == 'expired':
                await self.db.update_payment_status(payment_id, 'expired')
                await loading_msg.edit_text(
                    "⚠️ Payment expired.\n\n"
                    "Please create a new payment.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Back to Packages", callback_data="menu_buy")
                    ]])
                )
                
            else:
                await loading_msg.edit_text(
                    f"ℹ️ Payment Status: {status}\n\n"
                    f"Amount expected: {payment_data['amount_crypto']} {payment_data['currency'].upper()}\n"
                    f"Address: `{payment_data['pay_address']}`\n\n"
                    f"Please wait a few minutes and check again.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔄 Check Again", callback_data=f"check_payment_{payment_id}"),
                        InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_payment_{payment_id}")
                    ]]),
                    parse_mode='Markdown'
                )

        except Exception as e:
            self.logger.error(f"Payment check error: {str(e)}")
            await query.message.edit_text(
                "❌ Error checking payment status.\n\n"
                "Please try again or contact support.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Try Again", callback_data=f"check_payment_{payment_id}"),
                    InlineKeyboardButton("🔙 Back", callback_data="menu_buy")
                ]])
            )

    async def _process_successful_payment(self, payment_data: Dict) -> bool:
        """Process successful payment with atomic credit addition"""
        try:
            # Update payment status first
            status_updated = await self.db.update_payment_status(payment_data['payment_id'], 'completed')
            if not status_updated:
                self.logger.error(f"Failed to update payment status for {payment_data['payment_id']}")
                return False
            
            # Then add credits
            success = await self.db.add_credits(
                payment_data['user_id'], 
                payment_data['credits']
            )
            
            if success:
                self.logger.info(
                    f"Successfully processed payment {payment_data['payment_id']} "
                    f"for user {payment_data['user_id']}"
                )
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error processing payment: {str(e)}")
            return False

    async def handle_cancel_payment(self, query: CallbackQuery):
        """Handle payment cancellation"""
        try:
            payment_id = query.data.split('_')[2]
            
            # Update payment status
            await self.db.update_payment_status(payment_id, 'cancelled')
            
            await query.message.edit_text(
                "✅ Payment cancelled.\n\n"
                "You can create a new payment when ready.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back to Packages", callback_data="menu_buy")
                ]])
            )
            
        except Exception as e:
            self.logger.error(f"Error cancelling payment: {str(e)}")
            await query.message.edit_text(
                "❌ Error cancelling payment.\n\n"
                "Please try again or contact support.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back", callback_data="menu_buy")
                ]])
            )

    async def queue_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /queue command to show queue status (admin only)"""
        await QueueStatus.get_queue_status(
            analyzer_queue=self.analyzer,
            chat_id=update.effective_chat.id,
            user_id=update.effective_user.id
        )