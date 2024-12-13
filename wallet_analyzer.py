from collections import defaultdict
from typing import Dict, List
import logging
import requests
from datetime import datetime, timedelta
import os
import time

logger = logging.getLogger('TokenAnalyzer')

class WalletConnectionAnalyzer:
    def __init__(self):
        self.logger = logging.getLogger('TokenAnalyzer')
        self.basescan_api_key = os.getenv('BASESCAN_API_KEY')
        logger.info("WalletConnectionAnalyzer instance created")

    def analyze_wallet_connections(self, holders_data: List[Dict]) -> Dict:
        """Analyze connections between wallets in the top 50 holders"""
        try:
            # Filter out contract addresses and developer
            user_holders = [
                holder for holder in holders_data 
                if holder['address_type'] not in ['Contract', 'Developer']
            ]
            
            # Initialize analysis components
            creation_patterns = self._analyze_creation_patterns(user_holders)
            transaction_patterns = self._analyze_transaction_patterns(user_holders)
            recent_txs = self._analyze_recent_transactions(user_holders)
            
            if recent_txs:
                transaction_patterns.extend(recent_txs)
            
            # Find wallet clusters
            clusters = self._find_clusters(user_holders)
            
            # Generate risk score
            risk_score = self._calculate_risk_score(clusters, len(user_holders))
            
            # Return simplified data structure
            return {
                'risk_score': risk_score,
                'clusters': clusters,
                'creation_patterns': creation_patterns,
                'transaction_patterns': transaction_patterns
            }
            
        except Exception as e:
            self.logger.error(f"Error analyzing wallet connections: {str(e)}")
            return {}

    def _analyze_creation_patterns(self, holders: List[Dict]) -> List[Dict]:
        """Analyze wallet creation time patterns"""
        patterns = []
        
        # First get exact timestamps for each wallet using BaseScan API
        wallet_timestamps = {}
        for holder in holders:
            try:
                url = "https://api.basescan.org/api"
                params = {
                    'module': 'account',
                    'action': 'txlist',
                    'address': holder['address'],
                    'startblock': '0',
                    'endblock': '99999999',
                    'page': '1',
                    'offset': '1',
                    'sort': 'asc',
                    'apikey': self.basescan_api_key
                }
                
                response = requests.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    if data['status'] == '1' and data['result']:
                        first_tx = data['result'][0]
                        wallet_timestamps[holder['address']] = int(first_tx['timeStamp'])
            
                # Add small delay to avoid rate limiting
                time.sleep(0.1)
            
            except Exception as e:
                self.logger.error(f"Error getting timestamp for {holder['address']}: {str(e)}")
                continue
        
        # Now compare timestamps between wallets
        for i, wallet1 in enumerate(holders):
            addr1 = wallet1['address']
            if addr1 not in wallet_timestamps:
                continue
                
            for wallet2 in holders[i+1:]:
                addr2 = wallet2['address']
                if addr2 not in wallet_timestamps:
                    continue
                    
                try:
                    # Calculate time difference in minutes
                    time_diff_minutes = abs(wallet_timestamps[addr1] - wallet_timestamps[addr2]) / 60
                    
                    # Only consider wallets created within 30 minutes of each other
                    if time_diff_minutes <= 30:
                        balance_sum = wallet1['balance_percentage'] + wallet2['balance_percentage']
                        patterns.append({
                            'type': 'creation',
                            'wallets': [addr1, addr2],
                            'time_difference': time_diff_minutes,
                            'combined_balance': balance_sum,
                            'timestamp1': wallet_timestamps[addr1],
                            'timestamp2': wallet_timestamps[addr2]
                        })
                    
                except Exception as e:
                    self.logger.error(f"Error comparing timestamps: {str(e)}")
                    continue
        
        # Sort by time difference first, then by combined balance
        return sorted(patterns, key=lambda x: (x['time_difference'], -x['combined_balance']))

    def _analyze_transaction_patterns(self, holders: List[Dict]) -> List[Dict]:
        """Analyze transaction patterns between user wallets only"""
        patterns = []
        for i, wallet1 in enumerate(holders):
            for wallet2 in holders[i+1:]:
                try:
                    # Skip if either wallet has no transaction data
                    if not all(key in wallet1['activity_info'] for key in ['base_chain', 'ethereum']) or \
                       not all(key in wallet2['activity_info'] for key in ['base_chain', 'ethereum']):
                        continue
                    
                    # Compare transaction patterns
                    similarity = self._calculate_tx_similarity(wallet1, wallet2)
                    if similarity > 0.8:  # High similarity threshold
                        balance_sum = wallet1['balance_percentage'] + wallet2['balance_percentage']
                        patterns.append({
                            'type': 'transaction',
                            'wallets': [wallet1['address'], wallet2['address']],
                            'similarity': similarity,
                            'combined_balance': balance_sum,
                            'recent_activity': bool(wallet1['activity_info']['total_recent_tx_count'] or 
                                                  wallet2['activity_info']['total_recent_tx_count'])
                        })
                except KeyError:
                    continue
        
        return sorted(patterns, 
                     key=lambda x: (x['similarity'], x['combined_balance']), 
                     reverse=True)

    def _analyze_recent_transactions(self, holders: List[Dict]) -> List[Dict]:
        """Analyze direct transactions between holder wallets in the past 7 days"""
        patterns = []
        holder_addresses = {h['address'].lower() for h in holders}
        seven_days_ago = int((datetime.now() - timedelta(days=7)).timestamp())
        
        try:
            for holder in holders:
                address = holder['address']
                url = "https://api.basescan.org/api"
                params = {
                    'module': 'account',
                    'action': 'txlist',
                    'address': address,
                    'startblock': '0',
                    'endblock': '99999999',
                    'sort': 'desc',
                    'apikey': self.basescan_api_key
                }
                
                try:
                    response = requests.get(url, params=params)
                    if response.status_code == 200:
                        data = response.json()
                        if data['status'] == '1' and data['result']:
                            recent_txs = [
                                tx for tx in data['result']
                                if int(tx['timeStamp']) >= seven_days_ago and
                                tx['to'].lower() in holder_addresses and
                                not self._is_contract_transaction(tx)
                            ]
                            
                            for tx in recent_txs:
                                from_addr = tx['from'].lower()
                                to_addr = tx['to'].lower()
                                value_eth = float(tx['value']) / 1e18
                                
                                if value_eth > 0:  # Only consider non-zero value transactions
                                    patterns.append({
                                        'type': 'recent_transaction',
                                        'wallets': [from_addr, to_addr],
                                        'value_eth': value_eth,
                                        'timestamp': int(tx['timeStamp']),
                                        'tx_hash': tx['hash']
                                    })
                except Exception as e:
                    self.logger.error(f"Error getting transactions for {address}: {str(e)}")
                    continue
        
        except Exception as e:
            self.logger.error(f"Error in recent transaction analysis: {str(e)}")
        
        # Group transactions by wallet pairs
        tx_pairs = defaultdict(list)
        for pattern in patterns:
            pair = tuple(sorted(pattern['wallets']))
            tx_pairs[pair].append(pattern)
        
        # Aggregate transactions between same pairs
        aggregated_patterns = []
        for pair, txs in tx_pairs.items():
            total_value = sum(tx['value_eth'] for tx in txs)
            aggregated_patterns.append({
                'type': 'recent_transaction',
                'wallets': list(pair),
                'value_eth': total_value,
                'frequency': len(txs),
                'latest_timestamp': max(tx['timestamp'] for tx in txs)
            })
        
        return sorted(aggregated_patterns, 
                     key=lambda x: (x['frequency'], x['value_eth']), 
                     reverse=True)

    def _is_contract_transaction(self, tx: Dict) -> bool:
        """Check if transaction involves contract interaction"""
        return tx.get('input', '0x') != '0x'  # Non-zero input data indicates contract interaction

    def _calculate_tx_similarity(self, wallet1: Dict, wallet2: Dict) -> float:
        """Calculate transaction pattern similarity between two wallets"""
        try:
            # Compare Base chain activity
            base_tx1 = self._clean_tx_count(wallet1['activity_info']['base_chain']['total_tx_count'])
            base_tx2 = self._clean_tx_count(wallet2['activity_info']['base_chain']['total_tx_count'])
            
            # Compare Ethereum activity
            eth_tx1 = self._clean_tx_count(wallet1['activity_info']['ethereum']['total_tx_count'])
            eth_tx2 = self._clean_tx_count(wallet2['activity_info']['ethereum']['total_tx_count'])
            
            # Calculate ratios
            base_ratio = min(base_tx1, base_tx2) / max(base_tx1, base_tx2) if max(base_tx1, base_tx2) > 0 else 0
            eth_ratio = min(eth_tx1, eth_tx2) / max(eth_tx1, eth_tx2) if max(eth_tx1, eth_tx2) > 0 else 0
            
            # Weight Base activity more heavily
            similarity = (base_ratio * 0.7) + (eth_ratio * 0.3)
            
            # Consider activity timing
            both_active = (wallet1['activity_info']['is_active_overall'] and 
                         wallet2['activity_info']['is_active_overall'])
            
            return similarity * (1.2 if both_active else 0.8)
            
        except (KeyError, ValueError, ZeroDivisionError):
            return 0.0

    def _clean_tx_count(self, tx_count: str) -> int:
        """Clean transaction count string to integer"""
        if isinstance(tx_count, str):
            return int(tx_count.replace('+', ''))
        return int(tx_count) if tx_count else 0

    def _find_clusters(self, holders: List[Dict]) -> List[List[str]]:
        """Find clusters of connected wallets with stricter criteria"""
        clusters = []
        used_wallets = set()
        
        for i, wallet1 in enumerate(holders):
            if wallet1['address'] in used_wallets:
                continue
                
            current_cluster = [wallet1['address']]
            used_wallets.add(wallet1['address'])
            
            for wallet2 in holders[i+1:]:
                if wallet2['address'] in used_wallets:
                    continue
                    
                connection_weight = self._calculate_connection_weight(wallet1, wallet2)
                
                if connection_weight >= 0.8:  # Higher threshold for connection
                    current_cluster.append(wallet2['address'])
                    used_wallets.add(wallet2['address'])
            
            if len(current_cluster) > 1:
                clusters.append(current_cluster)
        
        return sorted(clusters, key=len, reverse=True)

    def _calculate_connection_weight(self, wallet1: Dict, wallet2: Dict) -> float:
        """Calculate connection weight between two wallets"""
        weight = 0.0
        
        try:
            # Creation time similarity (40%)
            time_diff = abs(wallet1['age_info']['wallet_age_days'] - 
                          wallet2['age_info']['wallet_age_days'])
            if time_diff < 1:
                weight += 0.4
            elif time_diff < 7:
                weight += 0.2
            
            # Transaction pattern similarity (40%)
            similarity = self._calculate_tx_similarity(wallet1, wallet2)
            weight += similarity * 0.4
            
            # Balance pattern similarity (20%)
            balance_diff = abs(wallet1['balance_percentage'] - wallet2['balance_percentage'])
            if balance_diff < 1:
                weight += 0.2
            elif balance_diff < 5:
                weight += 0.1
                
        except (KeyError, ValueError):
            pass
            
        return weight

    def _calculate_risk_score(self, clusters: List[List[str]], total_holders: int) -> Dict:
        """Calculate risk score based on wallet connections"""
        try:
            if total_holders == 0:
                return self._get_default_risk_score()

            # Analyze cluster characteristics
            largest_cluster = max(len(cluster) for cluster in clusters) if clusters else 0
            cluster_ratio = largest_cluster / total_holders
            
            # Calculate network density
            total_connections = sum(len(cluster) * (len(cluster) - 1) / 2 for cluster in clusters)
            max_possible_connections = total_holders * (total_holders - 1) / 2
            density = total_connections / max_possible_connections if max_possible_connections > 0 else 0
            
            # Calculate cluster distribution score
            cluster_sizes = [len(cluster) for cluster in clusters]
            avg_cluster_size = sum(cluster_sizes) / len(clusters) if clusters else 0
            size_variance = sum((size - avg_cluster_size) ** 2 for size in cluster_sizes) / len(clusters) if clusters else 0
            
            # Calculate risk score components
            cluster_score = min(cluster_ratio * 40, 40)  # Max 40 points
            density_score = min(density * 30, 30)  # Max 30 points
            variance_score = min((size_variance / total_holders) * 30, 30)  # Max 30 points
            
            risk_score = cluster_score + density_score + variance_score
            
            return {
                'score': min(risk_score, 100),
                'largest_cluster_size': largest_cluster,
                'num_clusters': len(clusters),
                'network_density': density,
                'risk_level': self._get_risk_level(risk_score),
                'components': {
                    'cluster_score': cluster_score,
                    'density_score': density_score,
                    'variance_score': variance_score
                }
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating risk score: {str(e)}")
            return self._get_default_risk_score()

    def _get_default_risk_score(self) -> Dict:
        """Return default risk score structure"""
        return {
            'score': 0,
            'largest_cluster_size': 0,
            'num_clusters': 0,
            'network_density': 0,
            'risk_level': 'Unknown',
            'components': {
                'cluster_score': 0,
                'density_score': 0,
                'variance_score': 0
            }
        }

    def _get_risk_level(self, score: float) -> str:
        """Convert risk score to risk level with emojis"""
        if score >= 80:
            return "🛑 Extreme Danger"
        elif score >= 60:
            return "🟧 Elevated Threat"
        elif score >= 40:
            return "🟡 Moderate Concern"
        elif score >= 20:
            return "🟢 Minimal Risk"
        else:
            return "✅ Negligible Threat"