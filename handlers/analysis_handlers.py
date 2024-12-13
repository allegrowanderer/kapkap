# handlers/analysis_handlers.py
import logging
from telegram.error import BadRequest

class AnalysisHandler:
    def __init__(self, db_manager, analyzer_queue, menu_handler, session_manager=None):
        self.db_manager = db_manager
        self.analyzer_queue = analyzer_queue
        self.menu_handler = menu_handler
        self.session_manager = session_manager
        self.logger = logging.getLogger('TokenAnalyzer')

    async def handle_analysis_type_selection(self, query, context):
        analysis_type = "quick" if query.data == "select_quick" else "deep"
        credits = 1 if analysis_type == "quick" else 5
        holders = 10 if analysis_type == "quick" else 50
        
        # Store in user session and context
        context.user_data['analysis_type'] = analysis_type
        session = self.session_manager.get_session(query.from_user.id)
        session.temp_data['analysis_type'] = analysis_type  # Temporary storage
        
        user_data = self.db_manager.get_user(query.from_user.id)
        if not user_data or user_data['credits'] < credits:
            await self.analyzer_queue.send_message(
                chat_id=query.message.chat_id,
                text=f"❌ Insufficient credits. Need {credits} credits.\n"
                     f"Your balance: {user_data['credits'] if user_data else 0}"
            )
            return
        
        address_prompt = (
            f"🔍 *{analysis_type.title()} Analysis Selected*\n\n"
            f"• Will analyze top {holders} holders\n"
            f"Please paste the token address below:\n"
            f"Example: `0x4F9Fd6Be4a90f2620860d680c0d4d5Fb53d1A825`"
        )
        
        try:
            await query.edit_message_text(
                text=address_prompt,
                parse_mode='Markdown'
            )
        except BadRequest:
            await self.analyzer_queue.send_message(
                chat_id=query.message.chat_id,
                text=address_prompt,
                parse_mode='Markdown'
            )

    async def handle_analysis_start(self, query, context):
        parts = query.data.split("_")
        analysis_type = parts[1]
        token_address = parts[2]
        
        user_data = self.db_manager.get_user(query.from_user.id)
        required_credits = 5 if analysis_type == "deep" else 1
        num_holders = 50 if analysis_type == "deep" else 10
        
        if not user_data or user_data['credits'] < required_credits:
            await self.analyzer_queue.send_message(
                chat_id=query.message.chat_id,
                text=f"❌ Insufficient credits. Need {required_credits} credits.\n"
                     f"Your balance: {user_data['credits'] if user_data else 0}"
            )
            return
        
        await self.analyzer_queue.send_message(
            chat_id=query.message.chat_id,
            text=f"🔄 Starting {analysis_type} analysis...\n"
                 f"Analyzing top {num_holders} holders\n"
                 f"This might take a few minutes..."
        )
        
        result = await self.analyzer_queue.add_task(
            token_address=token_address,
            chat_id=query.message.chat_id,
            user_id=query.from_user.id,
            analysis_type=analysis_type
        )
        
        if isinstance(result, dict) and result.get('error'):
            # If there's an error message, send it to the user
            await self.analyzer_queue.send_message(
                chat_id=query.message.chat_id,
                text=result['message'],
                parse_mode='Markdown'
            )
            return