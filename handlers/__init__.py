# handlers/__init__.py
from handlers.text_handlers import UserState
from .analysis_handlers import AnalysisHandler
from .view_handlers import ViewHandler
from .error_handlers import ErrorHandler
from .text_handlers import TextHandler
from telegram.error import BadRequest
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import logging

class HandlerManager:
    def __init__(self, db_manager, analyzer_queue, menu_handler, message_formatter, bot_commands, session_manager=None):
        self.db_manager = db_manager
        self.analyzer_queue = analyzer_queue
        self.menu_handler = menu_handler
        self.message_formatter = message_formatter
        self.bot_commands = bot_commands
        self.session_manager = session_manager
        self.analysis_handler = AnalysisHandler(db_manager, analyzer_queue, menu_handler, session_manager)
        self.view_handler = ViewHandler(analyzer_queue, message_formatter)
        self.error_handler = ErrorHandler(analyzer_queue)
        self.text_handler = TextHandler(db_manager, menu_handler, analyzer_queue, bot_commands, session_manager)
        self.logger = logging.getLogger('TokenAnalyzer')

    async def handle_callback(self, update, context):
        query = update.callback_query
        try:
            await query.answer()
            
            if self.session_manager:
                session = self.session_manager.get_session(query.from_user.id)
            
            if query.data.startswith('view_'):
                await self.handle_view_callback(query)
            elif query.data.startswith('analyze_'):
                await self.handle_analysis_start(query)
            elif query.data.startswith('select_'):
                await self.handle_analysis_type_selection(query)
            elif query.data.startswith('buy_'):
                await self.bot_commands.handle_buy_callback(query)
            elif query.data.startswith('check_payment_'):
                await self.bot_commands.handle_check_payment(query)
            elif query.data.startswith('menu_'):
                await self.handle_menu_callback(query, context)
            
        except Exception as e:
            self.logger.error(f"Error handling callback: {str(e)}")
            await self.analyzer_queue.send_message(
                chat_id=query.message.chat_id,
                text="❌ Error processing request. Please try again."
            )

    async def handle_menu_callback(self, query, context):
        """Handle menu callbacks"""
        try:
            if query.data == "menu_main":
                # Show main menu
                await query.edit_message_text(
                    text="Choose an option:",
                    reply_markup=self.menu_handler.get_main_menu(),
                    parse_mode='Markdown'
                )
            
            elif query.data == "menu_buy":
                # Show buy credits menu
                keyboard = [
                    [InlineKeyboardButton("📦 50 Credits - $20", callback_data="buy_basic")],
                    [InlineKeyboardButton("📦 75 Credits - $30", callback_data="buy_pro")],
                    [InlineKeyboardButton("📦 100 Credits - $40", callback_data="buy_premium")],
                    [InlineKeyboardButton("🔙 Back", callback_data="menu_main")]
                ]
                
                await query.edit_message_text(
                 
                    "if you ",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            
            elif query.data == "menu_analyze":
                # Show analysis menu
                analysis_menu = (
                    "🔎 *Select Analysis Type*\n\n"
                    "*Instant Analysis*\n"
                    "• Analysis of top 10 holders\n"
                    "• Basic risk assessment\n"
                    "• Developer background check\n"
                    "• Transaction history\n\n"
                )
                await query.edit_message_text(
                    text=analysis_menu,
                    reply_markup=self.menu_handler.get_analysis_type_menu(),
                    parse_mode='Markdown'
                )
            
            elif query.data == "menu_credits":
                # Show credits menu
                user_data = self.db_manager.get_user(query.from_user.id)
                if user_data:
                    credit_text = (
                        f"💳 *Credit Information*\n\n"
                        f"Your Balance: {user_data['credits']} credits\n\n"
                        f"*Analysis Costs:*\n"
                        f"• Quick Analysis (10 holders): 1 credit\n"
                        f"• Deep Analysis (50 holders): 5 credits\n\n"
                        f"*Purchase Credits:*\n"
                        f"Use /buy command to purchase credits"
                    )
                    await query.edit_message_text(
                        text=credit_text,
                        reply_markup=self.menu_handler.get_credits_menu(),
                        parse_mode='Markdown'
                    )
            
            elif query.data == "menu_history":
                # Show history menu (coming soon message)
                try:
                    coming_soon_text = (
                        "🚧 *Feature Under Development*\n\n"
                        "The Analysis History feature is currently under development.\n"
                        "This feature will allow you to:\n"
                        "• View your past analyses\n"
                        "• Track token performance\n"
                        "• Compare multiple analyses\n\n"
                        "Coming Soon! 🔜"
                    )
                    await query.edit_message_text(
                        text=coming_soon_text,
                        reply_markup=self.menu_handler.get_main_menu(),
                        parse_mode='Markdown'
                    )
                except BadRequest as e:
                    if "message is not modified" in str(e).lower():
                        await query.answer("Feature under development, coming soon! 🔜")
                    else:
                        raise
            
            elif query.data == "menu_help":
                # Show help menu
                help_text = (
                    "ℹ️ *Token Analyzer Bot Help*\n\n"
                    "*Commands:*\n"
                    "• /start - Start the bot\n"
                    "• /analyze <address> - Analyze token\n"
                    "• /buy - Purchase credits\n"
                    "• /credits - Check balance\n\n"
                    "*Analysis Types:*\n"
                    "🔍 *Instant Analysis*\n"
                    "• Top 10 holders\n"
                    "• Basic risk assessment\n"
                    "• Developer check\n\n"
                )
                await query.edit_message_text(
                    text=help_text,
                    reply_markup=self.menu_handler.get_help_menu(),
                    parse_mode='Markdown'
                )

        except Exception as e:
            if not isinstance(e, BadRequest) or "message is not modified" not in str(e).lower():
                await self.analyzer_queue.send_message(
                    chat_id=query.message.chat_id,
                    text=f"❌ Error handling menu: {str(e)}"
                )

    async def handle_analysis_type_selection(self, query):
        analysis_type = "deep" if query.data == "select_deep" else "quick"
        credits_needed = 5 if analysis_type == "deep" else 1
        holders = 50 if analysis_type == "deep" else 10
        
        user_id = query.from_user.id
        
        session = self.session_manager.get_session(user_id)
        session.temp_data['analysis_type'] = analysis_type
        self.session_manager.update_state(user_id, UserState.AWAITING_ADDRESS)
        
        prompt_text = (
            f"🔍 {analysis_type.title()} Analysis Selected\n\n"
            f"• Will analyze top {holders} holders\n"
            f"Please paste the token address below:\n"
            f"Example: `0x4F9Fd6Be4a90f2620860d680c0d4d5Fb53d1A825`"
        )
        
        try:
            await query.message.edit_text(
                prompt_text,
                parse_mode='Markdown'
            )
        except Exception as e:
            self.logger.error(f"Error updating message: {str(e)}")
            await self.analyzer_queue.send_message(
                chat_id=query.message.chat_id,
                text=prompt_text,
                parse_mode='Markdown'
            )

    async def handle_analysis_start(self, query):
        """Handle starting token analysis"""
        parts = query.data.split("_")
        if len(parts) != 3:
            return
        
        analysis_type = parts[1]
        token_address = parts[2]
        
        user_data = self.db_manager.get_user(query.from_user.id)
        required_credits = 5 if analysis_type == "deep" else 1
        
        if not user_data or user_data['credits'] < required_credits:
            await self.analyzer_queue.send_message(
                chat_id=query.message.chat_id,
                text=f"❌ Insufficient credits. Need {required_credits} credits.\n"
                     f"Your balance: {user_data['credits'] if user_data else 0}"
            )
            return
        
        await self.analyzer_queue.add_task(
            token_address=token_address,
            chat_id=query.message.chat_id,
            user_id=query.from_user.id,
            analysis_type=analysis_type
        )

    async def handle_view_callback(self, query):
        """Handle view-related callbacks"""
        try:
            # Get stored analysis results
            analysis_data = self.analyzer_queue.get_analysis_results(query.from_user.id)
            if not analysis_data:
                await self.analyzer_queue.send_message(
                    chat_id=query.message.chat_id,
                    text="❌ No analysis data found. Please run a new analysis."
                )
                return

            # Extract view type from callback data
            view_type = query.data.split('_')[1]

            # Handle different view types
            if view_type == 'summary':
                summary_message = self.message_formatter.format_analysis_summary(
                    analysis_data['summary_stats'],
                    analysis_data
                )
                await self.analyzer_queue.split_and_send_message(
                    chat_id=query.message.chat_id,
                    text=summary_message,
                    parse_mode='Markdown'
                )

            elif view_type == 'dev':
                dev_message = self.message_formatter.format_developer_info(
                    analysis_data['deployer_analysis']
                )
                await self.analyzer_queue.split_and_send_message(
                    chat_id=query.message.chat_id,
                    text=dev_message,
                    parse_mode='Markdown'
                )

            elif view_type == 'holders':
                holders_message = self.message_formatter.format_holders_table(
                    analysis_data['holders_analysis']
                )
                await self.analyzer_queue.split_and_send_message(
                    chat_id=query.message.chat_id,
                    text=holders_message,
                    parse_mode='Markdown'
                )

        except Exception as e:
            self.logger.error(f"Error handling view callback: {str(e)}")
            await self.analyzer_queue.send_message(
                chat_id=query.message.chat_id,
                text="❌ Error displaying analysis data."
            )