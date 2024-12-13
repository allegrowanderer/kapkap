# menu_handler.py

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import logging

class MenuHandler:
    def __init__(self, db_manager=None, analyzer_queue=None, session_manager=None):
        self.db_manager = db_manager
        self.analyzer_queue = analyzer_queue
        self.session_manager = session_manager
        self.logger = logging.getLogger('TokenAnalyzer')

    @staticmethod
    def get_main_menu() -> InlineKeyboardMarkup:
        keyboard = [
            [InlineKeyboardButton("🔍 Analyze Token", callback_data="menu_analyze")],
            [InlineKeyboardButton("👛 Check Credits", callback_data="menu_credits")],
            [InlineKeyboardButton("💳 Buy Credits", callback_data="menu_buy")],
            [InlineKeyboardButton("📜 Analysis History", callback_data="menu_history")],
            [InlineKeyboardButton("ℹ️ Help", callback_data="menu_help")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def get_credits_packages_menu() -> InlineKeyboardMarkup:
        keyboard = [
            [InlineKeyboardButton("📦 50 Credits - $20", callback_data="buy_basic")],
            [InlineKeyboardButton("📦 75 Credits - $30", callback_data="buy_pro")],
            [InlineKeyboardButton("📦 100 Credits - $40", callback_data="buy_premium")],
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def get_analysis_type_menu() -> InlineKeyboardMarkup:
        keyboard = [
            [InlineKeyboardButton("🔍 Quick Analysis - Top 10 (1 credit)", callback_data="select_quick")],
            [InlineKeyboardButton("🔬 ", callback_data="select_deep")],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_main")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def get_analysis_options(token_address: str, analysis_type: str = "quick") -> InlineKeyboardMarkup:
        keyboard = [
            [InlineKeyboardButton("🔍 Start Analysis", callback_data=f"analyze_{analysis_type}_{token_address}")],
            [InlineKeyboardButton("🔙 Change Analysis Type", callback_data="menu_analyze")],
            [InlineKeyboardButton("❌ Cancel", callback_data="menu_main")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def get_credits_menu() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back to Main Menu", callback_data="menu_main")
        ]])

    @staticmethod
    def get_help_menu() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back to Main Menu", callback_data="menu_main")
        ]])

    @staticmethod
    def get_analysis_menu(token_address: str, analysis_type: str = "quick") -> InlineKeyboardMarkup:
        keyboard = [
            [InlineKeyboardButton("📊 View Summary", callback_data=f"view_summary_{token_address}")],
            [InlineKeyboardButton("👨‍💻 Developer Info", callback_data=f"view_dev_{token_address}")],
            [InlineKeyboardButton("👥 Holders Analysis", callback_data=f"view_holders_{token_address}")]
        ]
        
        if analysis_type == "deep":
            keyboard.append([InlineKeyboardButton("🔗 Wallet Connections", callback_data=f"view_connections_{token_address}")])
        
        keyboard.append([InlineKeyboardButton("❌ Close", callback_data="menu_main")])
        return InlineKeyboardMarkup(keyboard)

    async def handle_menu_action(self, query, context):
        """Centralized menu action handler"""
        menu_actions = {
            'menu_credits': self.handle_credits_menu,
            'menu_help': self.handle_help_menu,
            'menu_main': self.handle_main_menu,
            'menu_analyze': self.handle_analyze_menu,
            'menu_history': self.handle_history_menu
        }
        
        action = menu_actions.get(query.data)
        if action:
            if self.session_manager:
                # Update user's last activity
                session = self.session_manager.get_session(query.from_user.id)
            await action(query, context)
        else:
            self.logger.warning(f"Unknown menu action: {query.data}")

    async def handle_credits_menu(self, query, context):
        user_data = self.db_manager.get_user(query.from_user.id)
        if not user_data:
            await self.analyzer_queue.send_message(
                chat_id=query.message.chat_id,
                text="❌ User not found. Please use /start"
            )
            return

        credit_text = (
            f"💳 *Credit Information*\n\n"
            f"Your Balance: {user_data['credits']} credits\n\n"
            f"*Analysis Costs:*\n"
            f"• Quick Analysis (10 holders): 1 credit\n"
            f"• Deep Analysis (50 holders): 5 credits\n\n"
            f"*Purchase Credits:*\n"
            f"Use /buy to purchase credits"
        )
        
        await self.send_or_edit_message(
            query,
            credit_text,
            markup=self.get_credits_menu()
        )

    async def handle_help_menu(self, query, context):
        help_text = (
            "ℹ️ *Token Analyzer Bot Help*\n\n"
            "*Commands:*\n"
            "• /start - Start the bot\n"
            "• /analyze <address> - Analyze token\n"
            "*Analysis Types:*\n"
            "🔍 *Instant Analysis*\n"
            "• Top 10 holders\n"
            "• Basic risk assessment\n"
            "• Developer check\n\n"
        )
        
        await self.send_or_edit_message(
            query,
            help_text,
            markup=self.get_help_menu()
        )

    async def handle_main_menu(self, query, context):
        await self.send_or_edit_message(
            query,
            "Choose an option:",
            markup=self.get_main_menu()
        )

    async def handle_analyze_menu(self, query, context):
        analysis_menu = (
            "🔎 *Select Analysis Type*\n\n"
            "*Instant Analysis*\n"
            "• Analysis of top 10 holders\n"
            "• Basic risk assessment\n"
            "• Developer background check\n"
            "• Transaction history\n\n"
        )
        
        await self.send_or_edit_message(
            query,
            analysis_menu,
            markup=self.get_analysis_type_menu()
        )

    async def handle_history_menu(self, query, context):
        await self.analyzer_queue.send_message(
            chat_id=query.message.chat_id,
            text="📜 Analysis history feature coming soon!"
        )

    async def send_or_edit_message(self, query, text, markup=None, parse_mode='Markdown'):
        try:
            await query.edit_message_text(
                text=text,
                reply_markup=markup,
                parse_mode=parse_mode
            )
        except Exception as e:
            await self.analyzer_queue.send_message(
                chat_id=query.message.chat_id,
                text=text,
                reply_markup=markup,
                parse_mode=parse_mode
            )