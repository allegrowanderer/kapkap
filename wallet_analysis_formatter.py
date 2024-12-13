# wallet_analysis_formatter.py
from typing import Dict, List
import logging
from datetime import datetime

class WalletAnalysisFormatter:
    def __init__(self):
        self.logger = logging.getLogger('TokenAnalyzer')

    def format_analysis_summary(self, analysis_data: Dict) -> str:
        """Format wallet analysis data into a concise Telegram summary"""
        try:
            if not analysis_data or not self._validate_data(analysis_data):
                return "❌ No valid wallet analysis data available."

            risk_score = analysis_data['risk_score']
            network_stats = analysis_data['network_stats']

            summary = (
                "🔍 *Wallet Connection Analysis*\n\n"
                
                "🎯 *Risk Assessment*\n"
                f"• Level: {risk_score['risk_level']}\n"
                f"• Score: {risk_score['score']:.1f}/100\n\n"
                
                "📊 *Network Overview*\n"
                f"• 👥 Connected Groups: {network_stats['connected_groups']}\n"
                f"• 📊 Largest Group: {network_stats['largest_group']} wallets\n"
                f"• 🔄 Network Density: {network_stats['density']:.3f}\n\n"
            )

            # Add significant patterns if found
            patterns = self._format_significant_patterns(analysis_data)
            if patterns:
                summary += patterns

            # Add risk insights
            summary += self._format_risk_insights(risk_score)

            return summary

        except Exception as e:
            self.logger.error(f"Error formatting analysis summary: {str(e)}")
            return "❌ Error creating analysis summary"

    def _format_significant_patterns(self, analysis_data: Dict) -> str:
        """Format the most significant patterns found"""
        patterns_text = ""
        
        # Creation patterns (show top 3 most significant)
        if analysis_data.get('creation_patterns'):
            patterns_text += "*⚠️ Suspicious Wallet Patterns*\n"
            for pattern in analysis_data['creation_patterns'][:3]:
                addr1, addr2 = pattern['wallets']
                patterns_text += (
                    f"• `{addr1[:6]}...{addr1[-4:]}` ↔️ `{addr2[:6]}...{addr2[-4:]}`\n"
                    f"  Created {pattern['time_difference']:.1f}h apart\n"
                    f"  Combined: {pattern['combined_balance']:.1f}%\n"
                )
            
            total_patterns = analysis_data['total_patterns']['creation']
            if total_patterns > 3:
                patterns_text += f"_...and {total_patterns - 3} more similar patterns_\n"
            patterns_text += "\n"

        # Recent transactions (show top 3 most significant)
        recent_txs = [p for p in analysis_data.get('transaction_patterns', []) 
                     if p.get('type') == 'recent_transaction' and p.get('value_eth', 0) > 0]
        
        if recent_txs:
            patterns_text += "*💸 Recent Interactions (7d)*\n"
            for tx in recent_txs[:3]:
                addr1, addr2 = tx['wallets']
                frequency = tx.get('frequency', 1)
                value = tx.get('value_eth', 0)
                patterns_text += (
                    f"• `{addr1[:6]}...{addr1[-4:]}` ↔️ `{addr2[:6]}...{addr2[-4:]}`\n"
                    f"  {frequency}x transfers, {value:.3f} ETH\n"
                )
            
            if len(recent_txs) > 3:
                patterns_text += f"_...and {len(recent_txs) - 3} more interactions_\n"
            patterns_text += "\n"

        return patterns_text

    def _format_risk_insights(self, risk_score: Dict) -> str:
        """Format risk insights based on risk score components"""
        insights = "\n🚨 *Key Risk Insights*\n"
        components = risk_score.get('components', {})
        
        # Add relevant insights based on component scores
        if components.get('cluster_score', 0) > 30:
            insights += "🚨 Significant clustering of wallets identified\n"
        
        if components.get('density_score', 0) > 20:
            insights += "🌐 Detected irregular relation with connection behaviors\n"
        
        if components.get('variance_score', 0) > 20:
            insights += "🧩 Questionable groupings of wallets observed\n"
        
        if all(score <= 20 for score in components.values()):
            insights += "🟢 No significant irregular patterns found\n"

        return insights

    def _validate_data(self, data: Dict) -> bool:
        """Validate the analysis data structure"""
        required_fields = ['risk_score', 'network_stats']
        return all(field in data for field in required_fields)

    def get_quick_alert_message(self, analysis_data: Dict) -> str:
        """Generate a quick alert message for high-risk cases"""
        if not analysis_data or not analysis_data.get('risk_score'):
            return None
            
        risk_score = analysis_data['risk_score']
        if risk_score['score'] >= 70:
            return (
                "⚠️ *Critical Risk Notification*\n\n"
                f"• Threat Level: {risk_score['risk_level']}\n"
                f"• Evaluation: {risk_score['score']:.1f}/100\n"
                "• Numerous concerning activities observed\n"
                "• Comprehensive review advised\n"
            )
        return None