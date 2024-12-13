from datetime import datetime

class QueueStatus:
    @staticmethod
    async def get_queue_status(analyzer_queue, chat_id: int, user_id: int):
        """Get queue status - admin only"""
        ADMIN_ID = 873072614  # Your Telegram ID
        
        if user_id != ADMIN_ID:
            await analyzer_queue.send_message(
                chat_id=chat_id,
                text="❌ This command is only available to administrators."
            )
            return
            
        try:
            message = "🔄 *Queue Status*\n\n"
            
            # Show currently processing task
            if analyzer_queue.current_task:
                token = analyzer_queue.current_task["token_address"]
                analysis_type = analyzer_queue.current_task["analysis_type"]
                user_id = analyzer_queue.current_task["user_id"]
                message += (
                    f"*Currently Processing:*\n"
                    f"Token: `{token}`\n"
                    f"Type: {analysis_type}\n"
                    f"User: `{user_id}`\n"
                    f"Waiting Users: {len(analyzer_queue.active_tokens[token]['users'])}\n\n"
                )
            
            # Show queued tasks
            if analyzer_queue.queue:
                message += "*Queued Tasks:*\n"
                for idx, task in enumerate(analyzer_queue.queue, 1):
                    message += (
                        f"{idx}. `{task['token_address']}`\n"
                        f"   Type: {task['analysis_type']}\n"
                        f"   User: `{task['user_id']}`\n"
                        f"   Time: {task['timestamp']}\n"
                    )
            else:
                message += "✅ No tasks in queue\n"
            
            # Show cached analyses
            if analyzer_queue.analysis_cache:
                message += "\n*Recent Analyses:*\n"
                for key, data in analyzer_queue.analysis_cache.items():
                    token = key.split('_')[0]
                    analysis_type = key.split('_')[1]
                    cache_age = datetime.now() - datetime.fromisoformat(data['timestamp'])
                    minutes_old = int(cache_age.total_seconds() / 60)
                    message += f"• `{token}` ({analysis_type}, {minutes_old}m old)\n"
            
            await analyzer_queue.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            await analyzer_queue.send_message(
                chat_id=chat_id,
                text="❌ Error getting queue status"
            ) 