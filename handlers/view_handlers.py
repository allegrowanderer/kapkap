# handlers/view_handlers.py
import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from wallet_analysis_formatter import WalletAnalysisFormatter

class ViewHandler:
    def __init__(self, analyzer_queue, message_formatter):
        self.analyzer_queue = analyzer_queue
        self.message_formatter = message_formatter
        self.logger = logging.getLogger('TokenAnalyzer')
        # Add formatter initialization
        self.wallet_formatter = WalletAnalysisFormatter()

    async def handle_view_callbacks(self, query):
        """Enhanced view callback handler with progress tracking"""
        try:
            # Show loading state
            progress_message = await query.message.reply_text(
                "📊 Loading analysis data..."
            )

            analysis_data = self.analyzer_queue.get_analysis_results(query.from_user.id)
            if not analysis_data:
                await progress_message.edit_text(
                    "❌ Analysis data not found. Please run a new analysis."
                )
                return

            view_type = query.data.split('_')[1]
            handler_method = getattr(self, f'handle_{view_type}_view', None)
            
            if handler_method:
                await handler_method(query, analysis_data)
            else:
                await progress_message.edit_text("❌ Invalid view type requested.")

        except Exception as e:
            self.logger.error(f"View handling error: {str(e)}")
            await self.analyzer_queue.send_message(
                chat_id=query.message.chat_id,
                text="❌ Error displaying analysis results."
            )
        finally:
            # Clean up loading message
            try:
                await progress_message.delete()
            except Exception:
                pass

    async def handle_summary_view(self, query, analysis_data):
        """Handle summary view of analysis results"""
        try:
            self._validate_analysis_data(analysis_data, 'summary_stats')
            summary_message = self.message_formatter.format_analysis_summary(
                analysis_data['summary_stats'],
                analysis_data
            )
            await self.analyzer_queue.split_and_send_message(
                chat_id=query.message.chat_id,
                text=summary_message,
                parse_mode='Markdown'
            )
        except ValueError as e:
            await self.analyzer_queue.send_message(
                chat_id=query.message.chat_id,
                text=f"❌ {str(e)}"
            )

    async def handle_dev_view(self, query, analysis_data):
        """Handle developer analysis view"""
        try:
            self._validate_analysis_data(analysis_data, 'deployer_analysis')
            dev_message = self.message_formatter.format_developer_info(
                analysis_data['deployer_analysis']
            )
            await self.analyzer_queue.split_and_send_message(
                chat_id=query.message.chat_id,
                text=dev_message,
                parse_mode='Markdown'
            )
        except ValueError as e:
            await self.analyzer_queue.send_message(
                chat_id=query.message.chat_id,
                text=f"❌ {str(e)}"
            )

    async def handle_full_view(self, query, analysis_data):
        """Handle full analysis view with all sections"""
        try:
            sections = {
                'deployer_analysis': self.message_formatter.format_developer_info,
                'holders_analysis': self.message_formatter.format_holders_table,
                'summary_stats': lambda data: self.message_formatter.format_analysis_summary(data, analysis_data),
                'risk_analysis': self.message_formatter.format_risk_analysis,
                'pattern_analysis': self.message_formatter.format_pattern_analysis
            }
            
            messages_sent = 0
            for section, formatter in sections.items():
                if section in analysis_data and analysis_data[section]:
                    msg = formatter(analysis_data[section])
                    await self.analyzer_queue.split_and_send_message(
                        chat_id=query.message.chat_id,
                        text=msg,
                        parse_mode='Markdown'
                    )
                    messages_sent += 1
            
            if messages_sent == 0:
                raise ValueError("No valid analysis sections found")
                
        except Exception as e:
            await self.analyzer_queue.send_message(
                chat_id=query.message.chat_id,
                text=f"❌ Error generating full analysis view: {str(e)}"
            )

    async def handle_pattern_view(self, query, analysis_data):
        """Handle pattern analysis view"""
        try:
            self._validate_analysis_data(analysis_data, 'pattern_analysis')
            pattern_message = self.message_formatter.format_pattern_analysis(
                analysis_data['pattern_analysis']
            )
            await self.analyzer_queue.split_and_send_message(
                chat_id=query.message.chat_id,
                text=pattern_message,
                parse_mode='Markdown'
            )
        except ValueError as e:
            await self.analyzer_queue.send_message(
                chat_id=query.message.chat_id,
                text=f"❌ {str(e)}"
            )

    async def handle_holders_view(self, query, analysis_data):
        """Handle holders analysis view"""
        try:
            self._validate_analysis_data(analysis_data, 'holders_analysis')
            holders_message = self.message_formatter.format_holders_table(
                analysis_data['holders_analysis']
            )
            await self.analyzer_queue.split_and_send_message(
                chat_id=query.message.chat_id,
                text=holders_message,
                parse_mode='Markdown'
            )
        except ValueError as e:
            await self.analyzer_queue.send_message(
                chat_id=query.message.chat_id,
                text=f"❌ {str(e)}"
            )

    async def handle_risk_view(self, query, analysis_data):
        """Handle risk analysis view"""
        try:
            self._validate_analysis_data(analysis_data, 'risk_analysis')
            risk_message = self.message_formatter.format_risk_analysis(
                analysis_data['risk_analysis']
            )
            await self.analyzer_queue.split_and_send_message(
                chat_id=query.message.chat_id,
                text=risk_message,
                parse_mode='Markdown'
            )
        except ValueError as e:
            await self.analyzer_queue.send_message(
                chat_id=query.message.chat_id,
                text=f"❌ {str(e)}"
            )

    async def refresh_view(self, query, view_type):
        """Refresh a specific view with updated data"""
        try:
            analysis_data = self.analyzer_queue.get_analysis_results(query.from_user.id)
            if not analysis_data:
                raise ValueError("No analysis data found")

            view_type_handlers = {
                'summary': self.handle_summary_view,
                'dev': self.handle_dev_view,
                'pattern': self.handle_pattern_view,
                'holders': self.handle_holders_view,
                'risk': self.handle_risk_view,
                'full': self.handle_full_view
            }

            handler = view_type_handlers.get(view_type)
            if handler:
                await handler(query, analysis_data)
            else:
                raise ValueError(f"Invalid view type: {view_type}")

        except Exception as e:
            self.logger.error(f"Error refreshing view: {str(e)}")
            await self.analyzer_queue.send_message(
                chat_id=query.message.chat_id,
                text=f"❌ Error refreshing view: {str(e)}"
            )

            
    async def handle_connections_view(self, query, analysis_data):
        """Handle wallet connections view"""
        try:
            if analysis_data.get('analysis_type') != 'deep':
                await self.analyzer_queue.send_message(
                    chat_id=query.message.chat_id,
                    text="❌ Connection analysis is only available for Deep Analysis."
                )
                return

            if not analysis_data.get('connection_analysis'):
                await self.analyzer_queue.send_message(
                    chat_id=query.message.chat_id,
                    text="❌ Connection analysis data not available."
                )
                return

            # Check for high-risk scenarios first
            alert_message = self.wallet_formatter.get_quick_alert_message(
                analysis_data['connection_analysis']
            )
            if alert_message:
                await self.analyzer_queue.send_message(
                    chat_id=query.message.chat_id,
                    text=alert_message,
                    parse_mode='Markdown'
                )

            # Format and send main analysis summary
            summary_message = self.wallet_formatter.format_analysis_summary(
                analysis_data['connection_analysis']
            )
            
            # Format and send connection details (for user wallets only)
            if analysis_data['connection_analysis'].get('clusters'):
                cluster_message = self._format_cluster_details(
                    analysis_data['connection_analysis']['clusters'],
                    analysis_data['holders_analysis']
                )
                summary_message += f"\n{cluster_message}"

            # Format and send significant patterns
            if analysis_data['connection_analysis'].get('patterns'):
                pattern_message = self._format_significant_patterns(
                    analysis_data['connection_analysis']['patterns']
                )
                summary_message += f"\n{pattern_message}"

            # Send the complete analysis
            await self.analyzer_queue.split_and_send_message(
                chat_id=query.message.chat_id,
                text=summary_message,
                parse_mode='Markdown'
            )

        except Exception as e:
            self.logger.error(f"Error handling connections view: {str(e)}")
            await self.analyzer_queue.send_message(
                chat_id=query.message.chat_id,
                text="❌ Error displaying wallet connections analysis."
            )


    def _format_cluster_details(self, clusters, holders_data):
        """Format cluster details with balance information"""
        if not clusters:
            return ""
            
        message = "\n👥 *Connected Wallet Groups*\n"
        for idx, cluster in enumerate(clusters[:3], 1):
            if len(cluster) > 1:
                total_balance = 0
                message += f"\n*Group #{idx}* ({len(cluster)} wallets)\n"
                
                # Show top 3 wallets by balance
                shown_wallets = []
                for address in cluster:
                    holder = next((h for h in holders_data if h['address'] == address), None)
                    if holder and holder['address_type'] not in ['Contract', 'Developer']:
                        shown_wallets.append((address, holder['balance_percentage']))
                        total_balance += holder['balance_percentage']
                
                # Sort by balance
                shown_wallets.sort(key=lambda x: x[1], reverse=True)
                
                # Show top 3 wallets
                for addr, balance in shown_wallets[:3]:
                    message += f"• `{addr[:6]}...{addr[-4:]}` ({balance:.2f}%)\n"
                
                if len(shown_wallets) > 3:
                    message += f"  _...and {len(shown_wallets)-3} more wallets_\n"
                    
                message += f"📊 Group total: {total_balance:.2f}%\n"
        
        if len(clusters) > 3:
            message += f"\n_...and {len(clusters)-3} more groups_"
            
        return message

    def _format_significant_patterns(self, patterns):
        """Format significant pattern findings"""
        if not patterns:
            return ""
            
        message = "\n🔍 *Significant Patterns*\n"
        
        # Filter and sort patterns by significance
        significant_patterns = [p for p in patterns if p.get('significance', 0) > 0.7]
        significant_patterns.sort(key=lambda x: x.get('significance', 0), reverse=True)
        
        for pattern in significant_patterns[:3]:
            pattern_type = pattern.get('type', 'unknown')
            if pattern_type == 'creation':
                message += (
                    f"• 🕒 Coordinated creation detected\n"
                    f"  {pattern.get('details', 'No details available')}\n"
                )
            elif pattern_type == 'transaction':
                message += (
                    f"• 💸 Related transaction pattern\n"
                    f"  {pattern.get('details', 'No details available')}\n"
                )
                
        if len(significant_patterns) > 3:
            message += f"\n_...and {len(significant_patterns)-3} more patterns_"
            
        return message

    def _validate_analysis_data(self, analysis_data, required_section):
        """Validate analysis data and required section existence"""
        if not analysis_data:
            raise ValueError("Analysis data not found")
        if required_section not in analysis_data:
            raise ValueError(f"{required_section} data not found")
        if not analysis_data[required_section]:
            raise ValueError(f"{required_section} data is empty")