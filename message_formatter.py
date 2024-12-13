from typing import Dict, List, Tuple
from datetime import datetime, timezone

class MessageFormatter:
    @staticmethod
    def format_holders_table(holders_data: List[Dict]) -> str:
        """Format holders data as a telegram-friendly table with emojis and tags"""
        current_time = datetime.now(timezone.utc)
        analysis_time = datetime.strptime(holders_data[0].get('analysis_time', current_time.strftime('%Y-%m-%d %H:%M:%S')), '%Y-%m-%d %H:%M:%S')
        analysis_time = analysis_time.replace(tzinfo=timezone.utc)
        
        time_diff = current_time - analysis_time
        data_freshness = "🟢 Real-time" if time_diff.seconds < 300 else "🟡 Recent" if time_diff.seconds < 3600 else "🔴 Delayed"
        
        message = "📊 *Top Holders Analysis*\n"
        message += f"🕒 Analysis Time: {analysis_time.strftime('%Y-%m-%d %H:%M:%S')} UTC ({data_freshness})\n\n"
        
        for idx, holder in enumerate(holders_data, 1):
            # Determine holder type and tags
            type_emoji = {
                "Contract": "📜",
                "Developer": "👨‍💻",
                "User": "👤",
                "Fresh Wallet": "🆕",
                "Bot": "🤖",
                "Likely Bot": "⚠️",
                "OG": "👑",
                "Blackhole": "🔥"
            }.get(holder["address_type"], "👤")
            
            # Determine tags
            tags = []
            age_days = holder['age_info']['wallet_age_days']
            tx_count = holder['activity_info']['total_recent_tx_count']
            
            if holder['address_type'] == 'Blackhole':
                tags = ["🔥 Burn Address"]
            elif holder['address_type'] == 'Developer':
                tags = ["👨‍💻 Token Developer"]
                if age_days < 30:
                    tags.append("⚠️ New Dev")
                if holder['balance_percentage'] > 20:
                    tags.append("⚠️ High Dev Holdings")
            else:
                if age_days < 7:
                    tags.append("🆕 Fresh Wallet")
                if tx_count > 1500:
                    tags.append("🤖 Bot")
                elif tx_count > 750:
                    tags.append("⚠️ Likely Bot")
                elif age_days > 360 and holder['nft_info']['eth_nfts']:
                    tags.append("👑 OG")
                elif holder['address_type'] == 'Contract':
                    tags.append("📜 Contract")
            
            tags_str = " | ".join(tags) if tags else "Normal"
            
            # Determine activity status
            activity = "✅" if holder["activity_info"]["is_active_overall"] else "❌"
            
            # Format NFT status
            nft_status = []
            if holder["nft_info"]["base_nfts"]:
                nft_status.append("Base✅")
            if holder["nft_info"]["eth_nfts"]:
                nft_status.append("ETH✅")
            nft_str = " ".join(nft_status) if nft_status else "❌"
            
            # Update balance formatting to show smaller amounts
            balance = holder['token_balance']
            balance_str = (
                f"{balance:.8f}" if balance < 0.01 else  # Show 8 decimals for very small amounts
                f"{balance:.4f}" if balance < 1 else     # Show 4 decimals for small amounts
                f"{balance:.2f}"                         # Show 2 decimals for larger amounts
            )
            
            # Create holder entry with special formatting for Developer
            if holder['address_type'] == 'Developer':
                entry = (
                    f"{idx}. {type_emoji} `{holder['address'][:6]}...{holder['address'][-4:]}` 👨‍💻\n"
                    f"   💰 Balance: `{balance_str}` ({holder['balance_percentage']:.4f}%)\n"
                    f"   ⏳ Age: {holder['age_info']['wallet_age_days']} days\n"
                    f"   🎨 NFTs: {nft_str}\n"
                    f"   📈 Activity: {activity} ({tx_count} tx/30d)\n"
                    f"   🏷️ Tags: {tags_str}\n"
                    f"   💼 ETH History: {holder['activity_info']['ethereum']['total_tx_display']} tx\n"
                    "➖➖➖➖➖➖➖➖➖➖\n"
                )
            else:
                entry = (
                    f"{idx}. {type_emoji} `{holder['address'][:6]}...{holder['address'][-4:]}`\n"
                    f"   💰 Balance: `{balance_str}` ({holder['balance_percentage']:.4f}%)\n"
                    f"   ⏳ Age: {holder['age_info']['wallet_age_days']} days\n"
                    f"   🎨 NFTs: {nft_str}\n"
                    f"   📈 Activity: {activity} ({tx_count} tx/30d)\n"
                    f"   🏷️ Tags: {tags_str}\n"
                    "➖➖➖➖➖➖➖➖➖➖\n"
                )
            message += entry
        
        return message

    @staticmethod
    def calculate_risk_score(analysis_data: Dict) -> Tuple[int, List[str], str]:
        """Calculate comprehensive risk score analyzing 50 holders"""
        risk_score = 0
        risk_factors = []
        holders = analysis_data['holders_analysis']

        # 1. OG Holder Analysis
        og_holders = sum(1 for h in holders if h['age_info']['wallet_age_days'] > 360 and h['nft_info']['eth_nfts'])
        og_percentage = (og_holders / len(holders)) * 100
        
        # Fix the OG percentage thresholds and messaging
        if og_percentage >= 35:
            risk_score -= 25
            risk_factors.append(f"✅ Strong OG holder base ({og_percentage:.1f}%)")
        elif og_percentage >= 25:
            risk_score -= 15
            risk_factors.append(f"✅ Solid OG holder base ({og_percentage:.1f}%)")
        elif og_percentage >= 10:
            risk_score -= 5
            risk_factors.append(f"✅ Some OG holder presence ({og_percentage:.1f}%)")
        # Remove any OG-related risk factors if percentage is too low
        if og_percentage < 10:
            risk_factors = [f for f in risk_factors if "OG holder" not in f]

        # Check OG presence in top holders
        top_10_ogs = sum(1 for h in holders[:10] 
                        if h['age_info']['wallet_age_days'] > 360 
                        and h['nft_info']['eth_nfts'])
        if top_10_ogs >= 6:
            risk_score -= 15
            risk_factors.append("✅ Strong OG presence in top holders")

        # 2. Concentration Risk Analysis
        top_holder_percent = holders[0]['balance_percentage']
        top_5_holders_percent = sum(h['balance_percentage'] for h in holders[:5])
        top_10_holders_percent = sum(h['balance_percentage'] for h in holders[:10])
        
        # Single wallet concentration
        if top_holder_percent > 50:
            risk_score += 30
            risk_factors.append("❌ Critical: Single wallet holds >50% supply")
        elif top_holder_percent > 30:
            risk_score += 20
            risk_factors.append("⚠️ High: Single wallet holds >30% supply")
        elif top_holder_percent > 15:
            risk_score += 10
            risk_factors.append("⚠️ Moderate: Single wallet holds >15% supply")

        # Group concentration
        if top_5_holders_percent > 80:
            risk_score += 15
            risk_factors.append("❌ Top 5 wallets control >80% supply")
        if top_10_holders_percent > 90:
            risk_score += 10
            risk_factors.append("⚠️ Top 10 wallets control >90% supply")

        # 3. Holder Age Analysis
        fresh_wallets = sum(1 for h in holders if h['age_info']['wallet_age_days'] < 7)
        new_wallets = sum(1 for h in holders if h['age_info']['wallet_age_days'] < 30)
        top_10_fresh = sum(1 for h in holders[:10] if h['age_info']['wallet_age_days'] < 7)
        
        if fresh_wallets >= 8:
            risk_score += 15
            risk_factors.append("🆕 High number of fresh wallets (<7 days)")
        elif fresh_wallets >= 5:
            risk_score += 10
            risk_factors.append("⚠️ Notable number of fresh wallets (<7 days)")
        
        if new_wallets >= 8:
            risk_score += 10
            risk_factors.append("⚠️ High concentration of new wallets (<30 days)")
        
        if top_10_fresh > 2:
            risk_score += 15
            risk_factors.append("❌ Multiple top 10 holders are fresh wallets")

        # 4. Bot Activity Analysis
        bot_wallets = sum(1 for h in holders if h['activity_info']['total_recent_tx_count'] > 9999)
        likely_bot_wallets = sum(1 for h in holders if 1000 < h['activity_info']['total_recent_tx_count'] <= 9999)
        
        if likely_bot_wallets >= 8:
            risk_score += 15
            risk_factors.append("⚠️ High number of likely bot wallets detected")
        elif likely_bot_wallets >= 5:
            risk_score += 10
            risk_factors.append("⚠️ Notable number of likely bot wallets detected")
        
        if bot_wallets >= 5:
            risk_score += 15
            risk_factors.append("🤖 High number of bot wallets detected")

        # 5. Wallet Pattern Analysis
        similar_age_pattern = 0
        for i in range(len(holders) - 1):
            if abs(holders[i]['age_info']['wallet_age_days'] - holders[i+1]['age_info']['wallet_age_days']) < 2:
                similar_age_pattern += 1
        
        if similar_age_pattern > 10:
            risk_score += 15
            risk_factors.append("⚠️ Suspicious pattern: Multiple wallets created at similar times")

        # 6. Cross-chain Activity
        low_eth_activity = sum(1 for h in holders[:20] 
                            if h['activity_info']['ethereum']['total_tx_count'] < 10 
                            and h['balance_percentage'] > 2)
        
        if low_eth_activity > 10:
            risk_score += 10
            risk_factors.append("⚠️ Many large holders have limited Ethereum activity")

        # 7. Developer Analysis
        if analysis_data.get('deployer_analysis'):
            dev = analysis_data['deployer_analysis']
            
            # Age checks
            if dev['age_info']['wallet_age_days'] < 30:
                risk_score += 15
                risk_factors.append("👨‍💻 Developer wallet is new (<30 days)")
            
            # Activity checks
            if not dev['activity_info']['ethereum']['total_tx_count']:
                risk_score += 10
                risk_factors.append("⚠️ Developer has no Ethereum history")
            
            # Balance checks
            if dev['balance_percentage'] > 20:
                risk_score += 15
                risk_factors.append("⚠️ Developer holds significant supply (>20%)")
            
            # Sophistication check
            if not (dev['nft_info']['eth_nfts'] or dev['nft_info']['base_nfts']) and \
            dev['activity_info']['ethereum']['total_tx_count'] < 50:
                risk_score += 10
                risk_factors.append("⚠️ Developer shows limited blockchain experience")

        # 8. Contract Holder Analysis
        contract_holders = sum(1 for h in holders if h['address_type'] == 'Contract')
        large_contract_holders = sum(1 for h in holders 
                                if h['address_type'] == 'Contract' 
                                and h['balance_percentage'] > 5)
        
        if large_contract_holders > 3:
            risk_score += 15
            risk_factors.append("⚠️ Multiple large contract holders detected")
        elif contract_holders > 10:
            risk_score += 10
            risk_factors.append("ℹ️ High number of contract holders")

        # 9. Activity Distribution
        inactive_large_holders = sum(1 for h in holders[:20] 
                                if not h['activity_info']['is_active_overall'] 
                                and h['balance_percentage'] > 2)
        
        if inactive_large_holders > 5:
            risk_score += 10
            risk_factors.append("⚠️ Multiple large holders are inactive")

        # Ensure risk score stays within bounds
        risk_score = max(0, min(risk_score, 100))

        # Determine risk level
        if risk_score >= 75:
            risk_level = "🔴 Very High Risk"
        elif risk_score >= 50:
            risk_level = "🟠 High Risk"
        elif risk_score >= 30:
            risk_level = "🟡 Medium Risk"
        elif risk_score >= 15:
            risk_level = "🟢 Low Risk"
        else:
            risk_level = "✅ Very Low Risk"

        return risk_score, risk_factors, risk_level

    @staticmethod
    def format_analysis_summary(summary_stats: Dict, analysis_data: Dict) -> str:
        """Format analysis summary with risk score"""
        risk_score, risk_factors, risk_level = MessageFormatter.calculate_risk_score(analysis_data)
        
        message = (
            "📊 *Token Analysis Summary*\n"
            f"🕒 Analysis Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
            f"👥 Total Wallets: {summary_stats['Total Wallets Analyzed']}\n"
            f"💹 Supply Coverage: {summary_stats['Total Supply Coverage']}\n"
            f"⏳ Average Wallet Age: {summary_stats['Average Wallet Age']:.1f} days\n\n"
            "*Holder Categories:*\n"
        )
        
        for category, count in summary_stats['Category Distribution'].items():
            if category:
                emoji = {
                    "Contract": "📜",
                    "Fresh Wallet": "🆕",
                    "Bot": "🤖",
                    "Likely Bot": "⚠️",
                    "OG": "👑",
                }.get(category, "👤")
                percentage = (count / summary_stats['Total Wallets Analyzed']) * 100
                message += f"{emoji} {category}: {count} ({percentage:.1f}%)\n"
        
        message += f"\n🎯 *Risk Assessment*\n"
        message += f"Risk Level: {risk_level}\n"
        message += f"Risk Score: {risk_score}/100\n\n"
        
        if risk_factors:
            message += "*Risk Factors:*\n"
            message += "\n".join(risk_factors)
        else:
            message += "✅ No major risk factors detected"
        
        return message

    def format_connection_analysis(self, connection_data: Dict) -> str:
        """Format wallet connection analysis results with improved risk assessment"""
        try:
            if not connection_data:
                return "❌ No connection analysis data available"

            # Initialize base risk metrics with higher weights
            cluster_risk = 0
            creation_risk = 0
            
            # Calculate cluster-based risk with increased sensitivity
            if connection_data['risk_score']['num_clusters'] > 3:  # Lowered threshold
                cluster_risk = 4  # Increased risk score
            elif connection_data['risk_score']['num_clusters'] > 2:
                cluster_risk = 3
            elif connection_data['risk_score']['num_clusters'] > 1:
                cluster_risk = 2
                
            # Increased risk for connected wallets
            if connection_data['risk_score']['largest_cluster_size'] > 5:
                cluster_risk += 4
            elif connection_data['risk_score']['largest_cluster_size'] > 3:
                cluster_risk += 3
            elif connection_data['risk_score']['largest_cluster_size'] > 1:
                cluster_risk += 2
                
            # More sensitive network density thresholds
            if connection_data['risk_score']['network_density'] > 0.05:
                cluster_risk += 4
            elif connection_data['risk_score']['network_density'] > 0.01:
                cluster_risk += 3
            elif connection_data['risk_score']['network_density'] > 0.005:
                cluster_risk += 2

            # Calculate creation pattern risk with higher penalties
            if connection_data.get('creation_patterns'):
                num_patterns = len(connection_data['creation_patterns'])
                time_diffs = [p.get('time_difference', 24) for p in connection_data['creation_patterns']]
                avg_time_diff = sum(time_diffs) / len(time_diffs) if time_diffs else 24
                
                # Increased risk for multiple patterns
                if num_patterns > 5:
                    creation_risk += 5
                elif num_patterns > 3:
                    creation_risk += 4
                elif num_patterns > 1:
                    creation_risk += 3
                    
                # More aggressive risk for close creation times
                if avg_time_diff < 0.5:  # Less than 30 minutes apart
                    creation_risk += 5
                elif avg_time_diff < 2:  # Less than 2 hours apart
                    creation_risk += 4
                elif avg_time_diff < 6:  # Less than 6 hours apart
                    creation_risk += 3

            # Calculate total risk with adjusted thresholds
            total_risk = cluster_risk + creation_risk
            
            if total_risk >= 6:  # Lowered threshold for high risk
                risk_level = "🔴 High Risk"
                risk_score = 85 + min(15, (total_risk - 6) * 3)
            elif total_risk >= 4:
                risk_level = "🟠 Moderate Risk"
                risk_score = 65 + ((total_risk - 4) * 10)
            elif total_risk >= 2:
                risk_level = "🟡 Medium Risk"
                risk_score = 45 + ((total_risk - 2) * 10)
            else:
                risk_level = "🟢 Low Risk"
                risk_score = max(20, total_risk * 20)

            message = (
                "🔗 *Wallet Connection Analysis*\n\n"
                "📊 *Network Statistics*\n"
                f"• Connected Groups: {connection_data['risk_score']['num_clusters']}\n"
                f"• Wallets per Group: {connection_data['risk_score']['largest_cluster_size']}\n"
                f"• Network Density: {connection_data['risk_score']['network_density']:.3f}\n"
            )

            # Add creation pattern summary if exists
            if connection_data.get('creation_patterns'):
                message += f" Suspicious Creation Patterns: {len(connection_data['creation_patterns'])}\n"
                if time_diffs:
                    message += f"• Average Creation Time Gap: {avg_time_diff:.1f} hours\n"

            message += (
                f"\n🎯 *Risk Assessment*\n"
                f"• Risk Level: {risk_level}\n"
                f"• Risk Score: {risk_score:.1f}/100\n"
            )

            # Add creation patterns if exist
            if connection_data.get('creation_patterns'):
                message += "\n*⏰ Creation Time Patterns*\n"
                # Filter patterns for <= 30 minutes
                close_patterns = [p for p in connection_data['creation_patterns'] 
                                 if p.get('time_difference', float('inf')) <= 30]
                
                for pattern in close_patterns[:5]:
                    addr1, addr2 = pattern['wallets']
                    minutes = pattern.get('time_difference', 0)
                    
                    # Format time string more precisely
                    if minutes < 1:
                        seconds = int(minutes * 60)
                        time_str = f"{seconds} seconds"
                    elif minutes < 2:
                        time_str = "1 minute"
                    else:
                        time_str = f"{int(minutes)} minutes"
                    
                    message += (
                        f"• `{addr1[:6]}...{addr1[-4:]}` ↔️ "
                        f"`{addr2[:6]}...{addr2[-4:]}`\n"
                        f"  Created within {time_str}\n"
                    )
                    
                remaining = len(close_patterns) - 5
                if remaining > 0:
                    message += f"_...and {remaining} more patterns within 30 minutes_\n"

            # Add clusters/groups
            if connection_data.get('clusters'):
                message += "\n*👥 Connected Wallet Groups*\n"
                for idx, cluster in enumerate(connection_data['clusters'], 1):
                    if len(cluster) > 1:
                        message += (
                            f"\n*Group #{idx}* ({len(cluster)} wallets)\n"
                            "• Addresses: "
                        )
                        # Show first few addresses
                        for addr in cluster[:3]:
                            message += f"`{addr[:6]}...{addr[-4:]}` "
                        if len(cluster) > 3:
                            message += f"\n  _...and {len(cluster) - 3} more_"

            return message

        except Exception as e:
            logger.error(f"Error formatting connection analysis: {str(e)}")
            return "❌ Error formatting wallet connection analysis."

    @staticmethod
    def format_developer_info(dev_data: Dict) -> str:
        """Format developer information with emojis"""
        template = (
            "👨‍💻 *Developer Analysis*\n"
            f"🕒 Analysis Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
            f"📍 Address: `{dev_data['address']}`\n"
            f"💼 Type: {dev_data['address_type']}\n"
            f"💰 Token Holdings: `{dev_data['token_balance']:.4f}`\n"
            f"📊 Share: `{dev_data['balance_percentage']:.2f}%`\n\n"
            "🔐 *Security Metrics*\n"
            f"📅 Account Age: {dev_data['age_info']['wallet_age_days']} days\n"
            f"🌐 Multi-chain: {'✅' if dev_data['activity_info']['ethereum']['total_tx_count'] > 0 else '❌'}\n"
            f"🎨 Has NFTs: {'✅' if dev_data['nft_info']['eth_nfts'] or dev_data['nft_info']['base_nfts'] else '❌'}\n\n"
            "📈 *Activity Overview*\n"
            f"Base Transactions: {dev_data['activity_info']['base_chain']['total_tx_display']}\n"
            f"ETH Transactions: {dev_data['activity_info']['ethereum']['total_tx_display']}\n"
            f"Recent Activity: {dev_data['activity_info']['total_recent_tx_count']} tx (30d)"
        )
        return template