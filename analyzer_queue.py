import os
import asyncio
from collections import deque
from datetime import datetime
import logging
from typing import Optional, Dict
import shutil
from analyze import TokenAnalyzer
from analyzeHoldersAndDeveloper import analyze_csvs
from message_formatter import MessageFormatter
from handlers.menu_handler import MenuHandler
from wallet_analyzer import WalletConnectionAnalyzer

class AnalyzerQueue:
    def __init__(self, db_manager):
        # Initialize logger first
        self.logger = logging.getLogger('TokenAnalyzer')
        
        # Rest of initialization
        self.queue = deque()
        self.processing = False
        self.current_task: Optional[Dict] = None
        self.results_dir = "data"
        self.db_manager = db_manager
        self.formatter = MessageFormatter()
        self.menu_handler = MenuHandler()
        self.concurrent_analyses = 0
        self.max_concurrent = 5
        self.analysis_lock = asyncio.Lock()
        
        # Initialize WalletConnectionAnalyzer
        try:
            self.wallet_analyzer = WalletConnectionAnalyzer()
            self.logger.info("WalletConnectionAnalyzer initialized successfully")
        except Exception as e:
            self.logger.error(f"Error initializing WalletConnectionAnalyzer: {str(e)}")
            self.wallet_analyzer = None
        
        # Store application instance for sending messages
        self.app = None
        
        # Analysis results storage
        self.analysis_results = {}
        
        # Active analysis tracking
        self.active_tokens = {}
        self.analysis_cache = {}
        
        # Create data directory if it doesn't exist
        os.makedirs(self.results_dir, exist_ok=True)

    def set_application(self, application):
        """Set the application instance for sending messages"""
        self.app = application
        self.logger.info("Application instance set in AnalyzerQueue")

    async def send_message(self, chat_id: int, text: str, **kwargs):
        """Helper method to send messages"""
        if self.app:
            try:
                await self.app.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    **kwargs
                )
            except Exception as e:
                self.logger.error(f"Error sending message: {str(e)}")

    async def split_and_send_message(self, chat_id: int, text: str, **kwargs):
        """Split long messages and send them in chunks"""
        MAX_MESSAGE_LENGTH = 4096
        
        if len(text) <= MAX_MESSAGE_LENGTH:
            await self.send_message(chat_id=chat_id, text=text, **kwargs)
            return

        chunks = []
        current_chunk = ""
        
        lines = text.split('\n')
        
        for line in lines:
            if len(current_chunk) + len(line) + 1 <= MAX_MESSAGE_LENGTH:
                current_chunk += line + "\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = line + "\n"
        
        if current_chunk:
            chunks.append(current_chunk)

        for i, chunk in enumerate(chunks):
            if i == 0:
                chunk = "📊 *Analysis Report (Part 1)*\n\n" + chunk
            else:
                chunk = f"📊 *Analysis Report (Part {i+1})*\n\n" + chunk
            
            await self.send_message(
                chat_id=chat_id,
                text=chunk,
                **kwargs
            )
            await asyncio.sleep(0.5)

    async def add_task(self, token_address: str, chat_id: int, user_id: int, analysis_type: str) -> bool:
        """Add a task to the queue with analysis type"""
        cache_key = f"{token_address}_{analysis_type}"
        
        # Check if token is currently being analyzed
        if token_address in self.active_tokens:
            current_analysis = self.active_tokens[token_address]
            current_type = current_analysis.get('analysis_type')
            
            # If same analysis type is running, add user to waiting list
            if current_type == analysis_type:
                if user_id not in current_analysis['results_sent']:
                    current_analysis['users'].add(user_id)
                    current_analysis['chat_ids'] = current_analysis.get('chat_ids', {})
                    current_analysis['chat_ids'][user_id] = chat_id
                    await self.send_message(
                        chat_id=chat_id,
                        text=f"⏳ *Analysis Request Queued*\n\n"
                             f"Your {analysis_type} analysis request for:\n"
                             f"`{token_address}`\n\n"
                             f"has been added to the queue.\n"
                             f"You'll receive the results once the analysis is complete.",
                        parse_mode='Markdown'
                    )
                return True
            
            # Different analysis type - proceed with new analysis
            credits_required = 5 if analysis_type == "deep" else 1
            user_data = self.db_manager.get_user(user_id)
            
            if not user_data or user_data['credits'] < credits_required:
                await self.send_message(
                    chat_id=chat_id,
                    text=f"❌ Insufficient credits. Need {credits_required} credits.\n"
                         f"Your balance: {user_data['credits'] if user_data else 0}"
                )
                return False
            
            # Deduct credits
            if not self.db_manager.use_credit(user_id, credits_required):
                await self.send_message(
                    chat_id=chat_id,
                    text=f"❌ Error deducting credits. Please try again."
                )
                return False

        # Check if queue is not empty (other analyses are pending)
        if len(self.queue) > 0:
            await self.send_message(
                chat_id=chat_id,
                text=f"⏳ *Analysis Request Queued*\n\n"
                     f"Your {analysis_type} analysis request for:\n"
                     f"`{token_address}`\n\n"
                     f"has been added to the queue.\n"
                     f"You'll receive the results once the analysis is complete.",
                parse_mode='Markdown'
            )

        # Create new task
        task = {
            "token_address": token_address,
            "chat_id": chat_id,
            "user_id": user_id,
            "analysis_type": analysis_type,
            "timestamp": datetime.now().isoformat()
        }
        
        # Deduct credits before starting new analysis
        credits_required = 5 if analysis_type == "deep" else 1
        user_data = self.db_manager.get_user(user_id)
        
        if not user_data or user_data['credits'] < credits_required:
            await self.send_message(
                chat_id=chat_id,
                text=f"❌ Insufficient credits. Need {credits_required} credits.\n"
                     f"Your balance: {user_data['credits'] if user_data else 0}"
            )
            return False
        
        # Deduct credits
        if not self.db_manager.use_credit(user_id, credits_required):
            await self.send_message(
                chat_id=chat_id,
                text=f"❌ Error deducting credits. Please try again."
            )
            return False
        
        self.queue.append(task)
        self.active_tokens[token_address] = {
            'users': {user_id},
            'results_sent': set(),
            'credits_deducted': {user_id},
            'analysis_type': analysis_type,
            'chat_ids': {user_id: chat_id}
        }
        
        if not self.processing:
            asyncio.create_task(self.process_queue())
        
        return True


    async def _send_analysis_results(self, chat_id: int, user_id: int, analysis_data: Dict, analysis_type: str):
        """Send analysis results to a user"""
        try:
            # Send developer analysis if available
            if analysis_data.get('deployer_analysis'):
                dev_message = self.formatter.format_developer_info(analysis_data['deployer_analysis'])
                await self.split_and_send_message(
                    chat_id=chat_id,
                    text=dev_message,
                    parse_mode='Markdown'
                )
                await asyncio.sleep(0.5)  # Add delay between messages

            # Send holders analysis
            if analysis_data.get('holders_analysis'):
                holders_message = self.formatter.format_holders_table(analysis_data['holders_analysis'])
                await self.split_and_send_message(
                    chat_id=chat_id,
                    text=holders_message,
                    parse_mode='Markdown'
                )
                await asyncio.sleep(0.5)  # Add delay between messages

            # Send summary
            if analysis_data.get('summary_stats'):
                summary_message = self.formatter.format_analysis_summary(
                    analysis_data['summary_stats'],
                    analysis_data
                )
                await self.split_and_send_message(
                    chat_id=chat_id,
                    text=summary_message,
                    parse_mode='Markdown'
                )
                await asyncio.sleep(0.5)  # Add delay between messages

            # Send connection analysis for deep analysis
            if analysis_type == "deep" and analysis_data.get('connection_analysis'):
                self.logger.info("Formatting connection analysis...")
                connections_message = self.formatter.format_connection_analysis(
                    analysis_data['connection_analysis']
                )
                if connections_message:  # Only send if there's a message
                    self.logger.info("Sending connection analysis...")
                    await self.split_and_send_message(
                        chat_id=chat_id,
                        text=connections_message,
                        parse_mode='Markdown'
                    )
                    await asyncio.sleep(0.5)  # Add delay between messages

                    # Send connection report file if it exists
                    if analysis_data.get('connection_report'):
                        report_path = analysis_data['connection_report']
                        if os.path.exists(report_path):
                            try:
                                await self.app.bot.send_document(
                                    chat_id=chat_id,
                                    document=open(report_path, 'rb'),
                                    caption="🔗 Wallet Connection Analysis Report"
                                )
                            except Exception as e:
                                self.logger.error(f"Error sending connection report: {str(e)}")

            # Get remaining credits
            user_data = self.db_manager.get_user(user_id)
            remaining_credits = user_data['credits'] if user_data else 0
            credits_used = 5 if analysis_type == "deep" else 1
            
            # Send completion message with appropriate menu
            menu_markup = self.menu_handler.get_analysis_menu(
                analysis_data['token_address'], 
                analysis_type
            )
            
            await self.send_message(
                chat_id=chat_id,
                text=f"✅ {analysis_type.title()} analysis complete!\n\n"
                    "Use the menu below to navigate through the results:",
                reply_markup=menu_markup,
                parse_mode='Markdown'
            )

        except Exception as e:
            self.logger.error(f"Error sending results to user {user_id}: {str(e)}")
            await self.send_message(
                chat_id=chat_id,
                text="❌ Error sending analysis results. Please try again later."
            )



    async def process_queue(self):
        """Process tasks in the queue"""
        if self.processing:
            return

        async with self.analysis_lock:
            self.processing = True
            
            while self.queue:
                self.current_task = None
                token_address = None
                complete_analysis = None

                try:
                    # Get task from queue
                    self.current_task = self.queue.popleft()
                    token_address = self.current_task["token_address"]
                    chat_id = self.current_task["chat_id"]
                    user_id = self.current_task["user_id"]
                    analysis_type = self.current_task["analysis_type"]
                    
                    # Initialize results tracking for this token if not exists
                    if token_address not in self.active_tokens:
                        self.active_tokens[token_address] = {
                            'users': {user_id},
                            'results_sent': set(),
                            'credits_deducted': set(),  # Track who has already paid
                            'analysis_type': analysis_type
                        }

                    try:
                        # Run analysis code...
                        num_holders = 50 if analysis_type == "deep" else 10
                        
                        # Send starting message
                        await self.send_message(
                            chat_id=chat_id,
                            text=f"🔍 Starting {analysis_type} analysis for token: `{token_address}`\n"
                                 f"Analyzing top {num_holders} holders, please wait...",
                            parse_mode='Markdown'
                        )

                        # Run analysis in thread pool
                        loop = asyncio.get_event_loop()
                        analyzer = TokenAnalyzer(num_holders=num_holders)
                        
                        # Run token analysis in thread pool
                        analysis = await loop.run_in_executor(
                            None,
                            analyzer.analyze_token,
                            token_address,
                            analysis_type  # Pass analysis type to analyzer
                        )
                        
                        # Run secondary analysis
                        analysis_df, summary_stats = await loop.run_in_executor(
                            None, 
                            analyze_csvs
                        )
                        
                        # Create complete analysis
                        complete_analysis = {
                            'token_address': token_address,
                            'contract_info': analysis.get('contract_info', {}),
                            'deployer_analysis': analysis.get('deployer_analysis', {}),
                            'holders_analysis': analysis.get('holders_analysis', []),
                            'summary_stats': dict(summary_stats) if summary_stats else {},
                            'analysis_df': analysis_df.to_dict() if analysis_df is not None else {},
                            'analysis_type': analysis_type,
                            'connection_analysis': analysis.get('connection_analysis')
                        }

                        # Cache the results
                        cache_key = f"{token_address}_{analysis_type}"
                        self.analysis_cache[cache_key] = {
                            'timestamp': datetime.now().isoformat(),
                            'data': complete_analysis
                        }

                        # Send results to waiting users
                        waiting_users = self.active_tokens[token_address]['users']
                        results_sent = self.active_tokens[token_address]['results_sent']
                        credits_deducted = self.active_tokens[token_address]['credits_deducted']
                        chat_ids = self.active_tokens[token_address].get('chat_ids', {})

                        for wait_user_id in waiting_users:
                            if wait_user_id not in results_sent:
                                # Get correct chat_id for this user
                                target_chat_id = chat_ids.get(wait_user_id, wait_user_id)
                                
                                # Store and send results
                                self.analysis_results[wait_user_id] = complete_analysis
                                
                                await self._send_analysis_results(
                                    target_chat_id,
                                    wait_user_id,
                                    complete_analysis,
                                    analysis_type
                                )
                                
                                # Mark results as sent
                                results_sent.add(wait_user_id)

                    except Exception as analysis_error:
                        # Refund credits if analysis fails
                        if user_id in self.active_tokens[token_address]['credits_deducted']:
                            try:
                                credits_required = 5 if analysis_type == "deep" else 1
                                await self.db_manager.add_credits(user_id, credits_required)
                                self.logger.info(f"Refunded {credits_required} credits to user {user_id} due to analysis failure")
                                
                                # Remove from credits_deducted set
                                self.active_tokens[token_address]['credits_deducted'].remove(user_id)
                                
                                await self.send_message(
                                    chat_id=chat_id,
                                    text=f"❌ Analysis failed. Your {credits_required} credits have been refunded.\n"
                                         f"Error: {str(analysis_error)}\n\n"
                                         f"Please try again or contact support if the issue persists."
                                )
                            except Exception as refund_error:
                                self.logger.error(f"Error refunding credits: {str(refund_error)}")
                                await self.send_message(
                                    chat_id=chat_id,
                                    text="❌ Analysis failed and there was an error refunding your credits.\n"
                                         "Please contact support for assistance."
                                )
                        raise analysis_error

                except Exception as e:
                    self.logger.error(f"Error processing task: {str(e)}")
                    if self.current_task:
                        error_message = (
                            f"❌ Error analyzing token: {str(e)}\n\n"
                            "Please verify:\n"
                            "1. Valid token address (checksum format)\n"
                            "2. Token is on Base Chain\n"
                            "3. Contract is verified\n"
                            "4. Sufficient liquidity exists\n\n"
                        )
                        await self.send_message(
                            chat_id=self.current_task["chat_id"],
                            text=error_message
                        )

                finally:
                    # Cleanup
                    if token_address in self.active_tokens:
                        self.active_tokens.pop(token_address, None)
                    self.current_task = None
                    
                    # Allow other tasks to process
                    await asyncio.sleep(0.1)

            self.processing = False


    async def _process_task(self, task):
        token_address = task["token_address"]
        initiator_chat_id = task["chat_id"]
        initiator_user_id = task["user_id"]
        analysis_type = task["analysis_type"]
        results_sent = set()

        
        try:
            num_holders = 50 if analysis_type == "deep" else 10
            
            # Send starting message
            await self.send_message(
                chat_id=chat_id,
                text=f"🔍 Starting {analysis_type} analysis for token: `{token_address}`\n"
                    f"Analyzing top {num_holders} holders, please wait...",
                parse_mode='Markdown'
            )

            # Run analysis in thread pool
            loop = asyncio.get_event_loop()
            analyzer = TokenAnalyzer(num_holders=num_holders)





            analysis = await loop.run_in_executor(
                None,
                analyzer.analyze_token,
                token_address
            )

            # Run secondary analysis 
            analysis_df, summary_stats = await loop.run_in_executor(
                None,
                analyze_csvs
            )

            # Run wallet connection analysis if deep analysis
            connection_analysis = None
            if analysis_type == "deep" and self.wallet_analyzer:
                try:
                    for holder in analysis['holders_analysis']:
                        holder['token_address'] = token_address

                    connection_analysis = await loop.run_in_executor(
                        None,
                        self.wallet_analyzer.analyze_wallet_connections,
                        analysis['holders_analysis']
                    )
                    self.logger.info("Wallet connection analysis completed")
                except Exception as e:
                    self.logger.error(f"Connection analysis error: {str(e)}")

            # Combine all analysis results
            complete_analysis = {
                'token_address': token_address,
                'contract_info': analysis.get('contract_info', {}),
                'deployer_analysis': analysis.get('deployer_analysis', {}),
                'holders_analysis': analysis.get('holders_analysis', []),
                'summary_stats': dict(summary_stats) if summary_stats else {},
                'analysis_df': analysis_df.to_dict() if analysis_df is not None else {},
                'analysis_type': analysis_type,
                'connection_analysis': connection_analysis
            }

            # Cache results
            self.analysis_cache[token_address] = {
                'timestamp': datetime.now().isoformat(),
                'data': complete_analysis
            }

            # Store results for user
            self.analysis_results[user_id] = complete_analysis


            # Store and send results
            waiting_users = self.active_tokens.get(token_address, {initiator_user_id})
            for wait_user_id in waiting_users:
                if wait_user_id not in results_sent:
                    self.analysis_results[wait_user_id] = complete_analysis
                    
                    # Get correct chat_id for each user
                    target_chat_id = initiator_chat_id if wait_user_id == initiator_user_id else wait_user_id
                    
                    await self._send_analysis_results(
                        target_chat_id,
                        wait_user_id,
                        complete_analysis,
                        analysis_type
                    )
                    results_sent.add(wait_user_id)

        except Exception as e:
            self.logger.error(f"Task processing error: {str(e)}")
            await self.send_message(
                chat_id=chat_id,
                text=f"❌ Error analyzing token: {str(e)}\n\n"
                        "Please verify:\n"
                        "1. Valid token address (checksum format)\n"
                        "2. Token is on Base Chain\n"
                        "3. Contract is verified\n"
                        "4. Sufficient liquidity exists"
            )
        finally:
            if token_address in self.active_tokens:
                self.active_tokens.pop(token_address)

    async def _run_analysis(self, token_address, num_holders, analysis_type, chat_id, user_id):
        """Run analysis in separate task"""
        analyzer = TokenAnalyzer(num_holders=num_holders)
        analysis = analyzer.analyze_token(token_address)
        
        analysis_df, summary_stats = analyze_csvs()
        
        connection_analysis = None
        if analysis_type == "deep" and self.wallet_analyzer:
            try:
                for holder in analysis['holders_analysis']:
                    holder['token_address'] = token_address
                connection_analysis = self.wallet_analyzer.analyze_wallet_connections(
                    analysis['holders_analysis']
                )
            except Exception as e:
                self.logger.error(f"Connection analysis error: {str(e)}")

        return {
            'token_address': token_address,
            'contract_info': analysis.get('contract_info', {}),
            'deployer_analysis': analysis.get('deployer_analysis', {}), 
            'holders_analysis': analysis.get('holders_analysis', []),
            'summary_stats': dict(summary_stats) if summary_stats else {},
            'analysis_df': analysis_df.to_dict() if analysis_df is not None else {},
            'analysis_type': analysis_type,
            'connection_analysis': connection_analysis
        }

    def get_queue_status(self) -> Dict:
        """Get current queue status"""
        return {
            "queue_length": len(self.queue),
            "processing": self.processing,
            "current_task": self.current_task,
            "active_tokens": len(self.active_tokens),
            "cached_analyses": len(self.analysis_cache)
        }

    def get_analysis_results(self, user_id: int) -> Optional[Dict]:
        """Get stored analysis results for a user"""
        return self.analysis_results.get(user_id)