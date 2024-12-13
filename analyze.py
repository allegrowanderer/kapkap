import os
import logging
from dotenv import load_dotenv
from web3 import Web3
from datetime import datetime, timedelta
import requests
import json
import csv
import time
import pandas as pd
from typing import List, Dict, Any
from functools import lru_cache
from wallet_analyzer import WalletConnectionAnalyzer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
    handlers=[
        logging.FileHandler('token_analysis.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('TokenAnalyzer')

class TokenAnalyzer:
    def __init__(self, num_holders: int = 100):
        """Initialize the TokenAnalyzer with API keys from environment variables"""
        logger.info("Initializing TokenAnalyzer...")
        
        # Load environment variables
        load_dotenv()
        
        self.covalent_api_key = os.getenv('COVALENT_API_KEY')
        self.basescan_api_key = os.getenv('BASESCAN_API_KEY')
        self.etherscan_api_key = os.getenv('ETHERSCAN_API_KEY')
        
        if not all([self.covalent_api_key, self.basescan_api_key, self.etherscan_api_key]):
            logger.error("Missing required API keys in .env file")
            raise ValueError("Missing required API keys in .env file")
        
        logger.info("API keys loaded successfully")
        
        # Use public RPC endpoints instead of Infura
        self.w3_base = Web3(Web3.HTTPProvider('https://mainnet.base.org'))
        self.w3_eth = Web3(Web3.HTTPProvider('https://eth.llamarpc.com'))
        self.num_holders = num_holders
        
        logger.info(f"Testing connections for {num_holders} holders analysis...")
        
        if not self._test_connection(self.w3_base, "Base"):
            logger.warning("Base RPC connection failed")
            
        if not self._test_connection(self.w3_eth, "Ethereum"):
            logger.info("Trying alternative Ethereum RPC...")
            alternative_rpcs = [
                'https://ethereum.publicnode.com',
                'https://rpc.ankr.com/eth',
                'https://1rpc.io/eth'
            ]
            for rpc in alternative_rpcs:
                logger.info(f"Attempting connection to {rpc}")
                self.w3_eth = Web3(Web3.HTTPProvider(rpc))
                if self._test_connection(self.w3_eth, "Ethereum"):
                    logger.info(f"Successfully connected to alternative Ethereum RPC: {rpc}")
                    break

        logger.info("Loading ERC20 ABI...")
        self.erc20_abi = json.loads('''[
            {"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"},
            {"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"},
            {"constant":true,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"type":"function"},
            {"constant":true,"inputs":[],"name":"totalSupply","outputs":[{"name":"","type":"uint256"}],"type":"function"},
            {"anonymous":false,"inputs":[{"indexed":true,"name":"from","type":"address"},{"indexed":true,"name":"to","type":"address"},{"indexed":false,"name":"value","type":"uint256"}],"name":"Transfer","type":"event"}
        ]''')
        logger.info("TokenAnalyzer initialization complete")
        
        # Add WalletConnectionAnalyzer initialization here
        self.wallet_analyzer = None
        if num_holders >= 50:
            try:
                self.wallet_analyzer = WalletConnectionAnalyzer()
                logger.info("WalletConnectionAnalyzer initialized successfully")
            except Exception as e:
                logger.error(f"Error initializing WalletConnectionAnalyzer: {str(e)}")


        
    def is_contract(self, address: str) -> bool:
        """Check if an address is a contract or regular user account"""
        try:
            checksummed_address = self.w3_base.to_checksum_address(address)
            code = self.w3_base.eth.get_code(checksummed_address)
            is_contract = len(code) > 0
            logger.debug(f"Contract check for {address[:8]}...: {'Yes' if is_contract else 'No'}")
            return is_contract
        except Exception as e:
            logger.error(f"Error checking if address is contract: {str(e)}")
            return False

    def get_address_type(self, address: str) -> str:
        """Determine if address is a contract, user account, or blackhole"""
        # Check for blackhole address first
        blackhole_addresses = [
            "0x000000000000000000000000000000000000dead",
            "0x0000000000000000000000000000000000000000",
            "0xdead000000000000000042069420694206942069",
            "0x0000000000000000000000000000000000000001"
        ]
        
        checksummed_address = self.w3_base.to_checksum_address(address)
        if checksummed_address.lower() in blackhole_addresses:
            logger.debug(f"Address type for {address[:8]}...: Blackhole")
            return "Blackhole"
        
        is_contract = self.is_contract(address)
        logger.debug(f"Address type for {address[:8]}...: {'Contract' if is_contract else 'User'}")
        return "Contract" if is_contract else "User"

    @lru_cache(maxsize=100)
    def get_top_holders(self, token_address: str, limit: int = None) -> List[str]:
        """Get top token holders with Covalent as primary and BaseScan as fallback"""
        logger.info(f"Getting top holders for {token_address}")
        checksummed_token = self.w3_base.to_checksum_address(token_address)
        
        # Try Covalent API first
        try:
            url = f"https://api.covalenthq.com/v1/8453/tokens/{checksummed_token}/token_holders/"
            headers = {
                "Authorization": f"Bearer {self.covalent_api_key}"
            }
            params = {
                "page-size": (limit or self.num_holders) * 2,  # Get extra to account for potential zero balances
                "page-number": 0,
                "quote-currency": "USD"
            }
            
            logger.info("Fetching holders from Covalent API...")
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()['data']
                holders = []
                token_contract = self.w3_base.eth.contract(address=checksummed_token, abi=self.erc20_abi)
                decimals = token_contract.functions.decimals().call()
                
                for item in data.get('items', []):
                    try:
                        holder_address = self.w3_base.to_checksum_address(item['address'])
                        # Verify with RPC call
                        current_balance = token_contract.functions.balanceOf(holder_address).call()
                        if current_balance > 0:
                            holders.append(holder_address)
                            logger.debug(f"Verified Covalent holder {holder_address[:8]}... "
                                       f"balance={current_balance/(10**decimals)}")
                            
                            if len(holders) >= (limit or self.num_holders):
                                break
                    except Exception as e:
                        logger.error(f"Error verifying Covalent holder: {str(e)}")
                        continue
                
                if holders:
                    logger.info(f"Found {len(holders)} verified holders from Covalent")
                    return holders[:limit or self.num_holders]
                else:
                    logger.warning("No valid holders found from Covalent, trying BaseScan...")
        
        except Exception as e:
            logger.error(f"Covalent API error: {str(e)}, falling back to BaseScan...")
        
        # Fallback to BaseScan if Covalent fails
        try:
            url = "https://api.basescan.org/api"
            params = {
                'module': 'token',
                'action': 'tokenholderlist',
                'contractaddress': checksummed_token,
                'apikey': self.basescan_api_key,
                'page': 1,
                'offset': (limit or self.num_holders) * 2,
                'sort': 'desc'
            }
            
            logger.info("Fetching holders from BaseScan API...")
            response = requests.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                if data['status'] == '1' and data['result']:
                    holders = []
                    token_contract = self.w3_base.eth.contract(address=checksummed_token, abi=self.erc20_abi)
                    decimals = token_contract.functions.decimals().call()
                    
                    for holder_data in data['result']:
                        try:
                            if isinstance(holder_data, dict) and 'TokenHolderAddress' in holder_data:
                                holder_address = self.w3_base.to_checksum_address(holder_data['TokenHolderAddress'])
                                current_balance = token_contract.functions.balanceOf(holder_address).call()
                                if current_balance > 0:
                                    holders.append(holder_address)
                                    logger.debug(f"Verified BaseScan holder {holder_address[:8]}... "
                                               f"balance={current_balance/(10**decimals)}")
                                    
                                    if len(holders) >= (limit or self.num_holders):
                                        break
                        except Exception as e:
                            logger.error(f"Error verifying BaseScan holder: {str(e)}")
                            continue
                    
                    if holders:
                        logger.info(f"Found {len(holders)} verified holders from BaseScan")
                        return holders[:limit or self.num_holders]
                    else:
                        logger.error("No valid holders found from BaseScan")
        
        except Exception as e:
            logger.error(f"BaseScan API error: {str(e)}")
        
        logger.error("All holder fetching methods failed")
        return []

    def _test_connection(self, w3, chain_name: str) -> bool:
        """Test Web3 connection"""
        try:
            w3.eth.block_number
            logger.info(f"Successfully connected to {chain_name}")
            return True
        except Exception as e:
            logger.error(f"Error connecting to {chain_name}: {str(e)}")
            return False

    def get_contract_info(self, token_address: str) -> Dict[str, Any]:
        """Get basic information about the token contract"""
        checksummed_token = self.w3_base.to_checksum_address(token_address)
        token_contract = self.w3_base.eth.contract(address=checksummed_token, abi=self.erc20_abi)
        symbol = token_contract.functions.symbol().call()
        decimals = token_contract.functions.decimals().call()
        return {"symbol": symbol, "decimals": decimals}

    def get_account_age(self, address: str) -> Dict[str, Any]:
        """Get accurate wallet age using blockchain explorers"""
        checksummed_address = self.w3_base.to_checksum_address(address)
        logger.info(f"Getting account age for {checksummed_address}")
        
        def get_first_tx_etherscan(address):
            if not self.etherscan_api_key:
                return None
                
            try:
                logger.debug(f"Querying Etherscan for {address[:8]}...")
                url = "https://api.etherscan.io/api"
                params = {
                    'module': 'account',
                    'action': 'txlist',
                    'address': address,
                    'startblock': '0',
                    'endblock': '99999999',
                    'page': '1',
                    'offset': '1',
                    'sort': 'asc',
                    'apikey': self.etherscan_api_key
                }
                
                response = requests.get(url, params=params)
                data = response.json()
                
                if data['status'] == '1' and data['result']:
                    first_tx = data['result'][0]
                    timestamp = datetime.fromtimestamp(int(first_tx['timeStamp']))
                    logger.info(f"First Ethereum transaction: {timestamp}")
                    return timestamp
                return None
            except Exception as e:
                logger.error(f"Etherscan error for {address}: {str(e)}")
                return None

        def get_first_tx_basescan(address):
            if not self.basescan_api_key:
                return None
                
            try:
                logger.debug(f"Querying Basescan for {address[:8]}...")
                url = "https://api.basescan.org/api"
                params = {
                    'module': 'account',
                    'action': 'txlist',
                    'address': address,
                    'startblock': '0',
                    'endblock': '99999999',
                    'page': '1',
                    'offset': '1',
                    'sort': 'asc',
                    'apikey': self.basescan_api_key
                }
                
                response = requests.get(url, params=params)
                data = response.json()
                
                if data['status'] == '1' and data['result']:
                    first_tx = data['result'][0]
                    timestamp = datetime.fromtimestamp(int(first_tx['timeStamp']))
                    logger.info(f"First Base transaction: {timestamp}")
                    return timestamp
                return None
            except Exception as e:
                logger.error(f"Basescan error for {address}: {str(e)}")
                return None

        # Get the earliest transaction timestamp
        timestamps = []
        
        eth_timestamp = get_first_tx_etherscan(checksummed_address)
        if eth_timestamp:
            timestamps.append(eth_timestamp)
            
        base_timestamp = get_first_tx_basescan(checksummed_address)
        if base_timestamp:
            timestamps.append(base_timestamp)
        
        if not timestamps:
            logger.warning(f"No transaction history found for {checksummed_address}")
            return {
                "older_than_30d": False,
                "older_than_90d": False,
                "older_than_180d": False,
                "older_than_360d": False,
                "first_activity": None,
                "wallet_age_days": 0
            }
            
        first_activity = min(timestamps)
        age = datetime.now() - first_activity
        age_days = age.days
        
        logger.info(f"First activity for {checksummed_address}: {first_activity.strftime('%Y-%m-%d')} ({age_days} days ago)")
        
        return {
            "older_than_30d": age_days > 30,
            "older_than_90d": age_days > 90,
            "older_than_180d": age_days > 180,
            "older_than_360d": age_days > 360,
            "first_activity": first_activity.strftime("%Y-%m-%d"),
            "wallet_age_days": age_days
        }




    def check_nfts(self, address: str) -> Dict[str, Any]:
            """Enhanced NFT detection using block explorers"""
            checksummed_address = self.w3_base.to_checksum_address(address)
            logger.info(f"Checking NFT holdings for {checksummed_address}")
            
            def get_erc721_transfers_etherscan():
                try:
                    url = "https://api.etherscan.io/api"
                    params = {
                        'module': 'account',
                        'action': 'tokennfttx',  # ERC-721 transfers
                        'address': checksummed_address,
                        'page': 1,
                        'offset': 1,  # We just need to know if they have any
                        'sort': 'desc',
                        'apikey': self.etherscan_api_key
                    }
                    
                    response = requests.get(url, params=params)
                    if response.status_code == 200:
                        data = response.json()
                        return data['status'] == '1' and len(data.get('result', [])) > 0
                    return False
                except Exception as e:
                    logger.error(f"Etherscan NFT check error: {str(e)}")
                    return False

            def get_erc721_transfers_basescan():
                try:
                    url = "https://api.basescan.org/api"
                    params = {
                        'module': 'account',
                        'action': 'tokennfttx',  # ERC-721 transfers
                        'address': checksummed_address,
                        'page': 1,
                        'offset': 1,  # We just need to know if they have any
                        'sort': 'desc',
                        'apikey': self.basescan_api_key
                    }
                    
                    response = requests.get(url, params=params)
                    if response.status_code == 200:
                        data = response.json()
                        return data['status'] == '1' and len(data.get('result', [])) > 0
                    return False
                except Exception as e:
                    logger.error(f"Basescan NFT check error: {str(e)}")
                    return False
            
            # Check Base Chain NFTs
            logger.info("Checking Base Chain NFTs...")
            base_nfts = get_erc721_transfers_basescan()
            
            # Check Ethereum NFTs
            logger.info("Checking Ethereum NFTs...")
            eth_nfts = get_erc721_transfers_etherscan()
            
            logger.info(f"NFT holdings for {checksummed_address}:")
            logger.info(f"Base NFTs: {base_nfts}")
            logger.info(f"ETH NFTs: {eth_nfts}")
            
            return {
                "base_nfts": base_nfts,
                "eth_nfts": eth_nfts
            }


    

    def check_wallet_activity(self, address: str) -> Dict[str, Any]:
            """Get accurate transaction counts from block explorers"""
            checksummed_address = self.w3_base.to_checksum_address(address)
            thirty_days_ago = int((datetime.now() - timedelta(days=30)).timestamp())
            
            logger.info(f"Checking wallet activity for {checksummed_address}")
            
            def get_etherscan_transactions():
                try:
                    logger.debug("Querying Etherscan for transactions")
                    url = "https://api.etherscan.io/api"
                    recent_params = {
                        'module': 'account',
                        'action': 'txlist',
                        'address': checksummed_address,
                        'startblock': '0',
                        'endblock': '99999999',
                        'sort': 'desc',
                        'apikey': self.etherscan_api_key
                    }
                    
                    response = requests.get(url, params=recent_params)
                    if response.status_code == 200:
                        data = response.json()
                        if data['status'] == '1' and data['result']:
                            txs = data['result']
                            recent_tx = sum(1 for tx in txs if int(tx['timeStamp']) >= thirty_days_ago)
                            
                            # Get total transaction count
                            total_params = {
                                'module': 'proxy',
                                'action': 'eth_getTransactionCount',
                                'address': checksummed_address,
                                'tag': 'latest',
                                'apikey': self.etherscan_api_key
                            }
                            total_response = requests.get(url, params=total_params)
                            if total_response.status_code == 200:
                                total_data = total_response.json()
                                if 'result' in total_data:
                                    total_tx = int(total_data['result'], 16)
                                    logger.info(f"Ethereum transactions - Total: {total_tx}, Recent: {recent_tx}")
                                    return total_tx, recent_tx
                    
                    logger.warning("Failed to get Ethereum transaction data")
                    return 0, 0
                except Exception as e:
                    logger.error(f"Etherscan error: {str(e)}")
                    return 0, 0

            def get_basescan_transactions():
                try:
                    logger.debug("Querying Basescan for transactions")
                    url = "https://api.basescan.org/api"
                    params = {
                        'module': 'account',
                        'action': 'txlist',
                        'address': checksummed_address,
                        'startblock': '0',
                        'endblock': '99999999',
                        'sort': 'desc',
                        'apikey': self.basescan_api_key
                    }
                    
                    response = requests.get(url, params=params)
                    if response.status_code == 200:
                        data = response.json()
                        if data['status'] == '1' and data['result']:
                            txs = data['result']
                            total_tx = len(txs)
                            recent_tx = sum(1 for tx in txs if int(tx['timeStamp']) >= thirty_days_ago)
                            logger.info(f"Base transactions - Total: {total_tx}, Recent: {recent_tx}")
                            return total_tx, recent_tx
                    
                    logger.warning("Failed to get Base transaction data")
                    return 0, 0
                except Exception as e:
                    logger.error(f"BaseScan error: {str(e)}")
                    return 0, 0

            base_total_tx, base_recent_tx = get_basescan_transactions()
            eth_total_tx, eth_recent_tx = get_etherscan_transactions()

            def format_tx_count(count):
                formatted = f"{count}+" if count >= 1000 else str(count)
                logger.debug(f"Formatted transaction count {count} as {formatted}")
                return formatted

            activity_data = {
                "base_chain": {
                    "is_active": base_recent_tx > 0,
                    "recent_tx_count": base_recent_tx,
                    "total_tx_count": base_total_tx,
                    "total_tx_display": format_tx_count(base_total_tx)
                },
                "ethereum": {
                    "is_active": eth_recent_tx > 0,
                    "recent_tx_count": eth_recent_tx,
                    "total_tx_count": eth_total_tx,
                    "total_tx_display": format_tx_count(eth_total_tx)
                },
                "total_recent_tx_count": base_recent_tx + eth_recent_tx,
                "total_tx_count": base_total_tx + eth_total_tx,
                "total_tx_display": format_tx_count(base_total_tx + eth_total_tx),
                "is_active_overall": (base_recent_tx + eth_recent_tx) > 0
            }

            logger.info(f"Activity analysis for {checksummed_address}:")
            logger.info(f"Base Chain: {activity_data['base_chain']['total_tx_display']} total, {base_recent_tx} recent")
            logger.info(f"Ethereum: {activity_data['ethereum']['total_tx_display']} total, {eth_recent_tx} recent")
            logger.info(f"Total recent transactions: {activity_data['total_recent_tx_count']}")
            logger.info(f"Overall active: {'Yes' if activity_data['is_active_overall'] else 'No'}")

            return activity_data




    def analyze_holder(self, token_address: str, holder_address: str, total_supply: float) -> Dict[str, Any]:
        """Analyze a single holder's wallet with better error handling"""
        try:
            checksummed_token = self.w3_base.to_checksum_address(token_address)
            checksummed_holder = self.w3_base.to_checksum_address(holder_address)
            
            logger.info(f"\nAnalyzing holder {checksummed_holder}...")
            
            # Get all data with retries if needed
            age_info = self.get_account_age(checksummed_holder)
            logger.info(f"Wallet age: {age_info['wallet_age_days']} days")
            
            token_balance = self.get_token_balance(checksummed_token, checksummed_holder)
            balance_percentage = (token_balance / total_supply * 100) if total_supply > 0 else 0
            logger.info(f"Token balance: {token_balance} ({balance_percentage:.4f}%)")
            
            # Get NFT info with retry
            nft_info = self.check_nfts(checksummed_holder)
            logger.info(f"NFT status - Base: {nft_info['base_nfts']}, ETH: {nft_info['eth_nfts']}")
            
            # Get transaction counts with retry
            activity_info = self.check_wallet_activity(checksummed_holder)
            logger.info(f"Recent activity: {activity_info['total_recent_tx_count']} transactions")
            
            return {
                "address": checksummed_holder,
                "token_balance": token_balance,
                "balance_percentage": balance_percentage,
                "age_info": age_info,
                "nft_info": nft_info,
                "activity_info": activity_info
            }
        except Exception as e:
            logger.error(f"Error analyzing holder {holder_address}: {str(e)}")
            return None





    def get_token_balance(self, token_address: str, holder_address: str) -> float:
        """Get token balance for a specific holder with RPC verification"""
        checksummed_token = self.w3_base.to_checksum_address(token_address)
        checksummed_holder = self.w3_base.to_checksum_address(holder_address)
        
        logger.info(f"Getting token balance for holder {checksummed_holder}")
        
        try:
            # First try direct RPC call for most current balance
            token_contract = self.w3_base.eth.contract(address=checksummed_token, abi=self.erc20_abi)
            balance = token_contract.functions.balanceOf(checksummed_holder).call()
            decimals = token_contract.functions.decimals().call()
            rpc_balance = balance / (10 ** decimals)
            
            # Format very small balances appropriately
            if rpc_balance < 1e-8:
                formatted_balance = f"{rpc_balance:.18f}"  # Show more decimals for tiny amounts
            elif rpc_balance < 1e-4:
                formatted_balance = f"{rpc_balance:.10f}"  # Show more decimals for small amounts
            else:
                formatted_balance = f"{rpc_balance:.8f}"   # Standard precision for normal amounts
            
            logger.info(f"Balance: {formatted_balance}")
            return rpc_balance
            
        except Exception as e:
            logger.error(f"Error getting token balance: {str(e)}")
            return 0.0

    def generate_csv_report(self, analysis_results: Dict[str, Any], output_file: str):
        """Enhanced CSV report with better balance formatting"""
        rows = []
        
        for holder_data in analysis_results["holders_analysis"]:
            if holder_data:
                # Format balance based on size
                balance = holder_data["token_balance"]
                if balance < 1e-8:
                    balance_str = f"{balance:.18f}"
                elif balance < 1e-4:
                    balance_str = f"{balance:.10f}"
                else:
                    balance_str = f"{balance:.8f}"

                row = {
                    "Address Type": holder_data["address_type"],
                    "Address": holder_data["address"],
                    "Token Balance": balance_str,  # Use formatted balance string
                    "% of Total Supply": f"{holder_data['balance_percentage']:.8f}%",  # More precision
                    "Wallet Age (days)": holder_data["age_info"]["wallet_age_days"],
                    "First Activity": holder_data["age_info"]["first_activity"],
                    "Older than 30d": holder_data["age_info"]["older_than_30d"],
                    "Older than 90d": holder_data["age_info"]["older_than_90d"],
                    "Older than 180d": holder_data["age_info"]["older_than_180d"],
                    "Older than 360d": holder_data["age_info"]["older_than_360d"],
                    "Has Base NFTs": holder_data["nft_info"]["base_nfts"],
                    "Has ETH NFTs": holder_data["nft_info"]["eth_nfts"],
                    "Total Base TX": holder_data["activity_info"]["base_chain"]["total_tx_display"],
                    "Base TX (30d)": holder_data["activity_info"]["base_chain"]["recent_tx_count"],
                    "Total ETH TX": holder_data["activity_info"]["ethereum"]["total_tx_display"],
                    "ETH TX (30d)": holder_data["activity_info"]["ethereum"]["recent_tx_count"],
                    "Total TX Count": holder_data["activity_info"]["total_tx_display"]
                }
                rows.append(row)
        
        df = pd.DataFrame(rows)
        df.to_csv(output_file, index=False)
        print(f"Holders report generated: {output_file}")






    def get_contract_deployer(self, token_address: str) -> str:
        """Get the contract deployer address using block explorer APIs"""
        checksummed_token = self.w3_base.to_checksum_address(token_address)
        
        try:
            # Try BaseScan API first
            url = "https://api.basescan.org/api"
            params = {
                'module': 'contract',
                'action': 'getcontractcreation',
                'contractaddresses': checksummed_token,
                'apikey': self.basescan_api_key
            }
            
            response = requests.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                if data['status'] == '1' and data['result']:
                    return self.w3_base.to_checksum_address(data['result'][0]['contractCreator'])
                    
            # Alternative: Get first internal transaction
            params = {
                'module': 'account',
                'action': 'txlistinternal',
                'address': checksummed_token,
                'startblock': '0',
                'endblock': '99999999',
                'sort': 'asc',
                'apikey': self.basescan_api_key
            }
            
            response = requests.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                if data['status'] == '1' and data['result']:
                    return self.w3_base.to_checksum_address(data['result'][0]['from'])
        
        except Exception as e:
            print(f"Error getting contract deployer: {str(e)}")
        
        return None




    def get_total_supply(self, token_address: str) -> float:
        """Get total supply of the token using Infura"""
        try:
            checksummed_token = self.w3_base.to_checksum_address(token_address)
            token_contract = self.w3_base.eth.contract(address=checksummed_token, abi=self.erc20_abi)
            
            # Get total supply and decimals directly from the contract
            total_supply = token_contract.functions.totalSupply().call()
            decimals = token_contract.functions.decimals().call()
            
            return total_supply / (10 ** decimals)
            
        except Exception as e:
            logger.error(f"Error getting total supply: {str(e)}")
            return 0


    def analyze_token(self, token_address: str, analysis_type: str = "quick") -> Dict[str, Any]:
        """Main analysis function with wallet connection analysis for deep scanning"""
        try:
            logger.info(f"\n{'='*50}\nStarting analysis for token: {token_address}")
            checksummed_token = self.w3_base.to_checksum_address(token_address)
            
            # Check if address is a token contract
            if not self.is_valid_token_contract(checksummed_token):
                logger.warning(f"Address {token_address} is not a valid token contract")
                return {
                    'error': True,
                    'message': (
                        "❌ This address appears to be a regular contract, not a token.\n\n"
                        "Please provide a valid token contract address.\n"
                        "Example: `0x2584c157b72f58eE1EC1c267f69fAc211B15D33E`"
                    )
                }
            
            logger.info(f"Target number of holders: {self.num_holders}")
            
            # Use the class instance instead of creating a new one
            wallet_analyzer = self.wallet_analyzer
            
            # Get contract info
            logger.info("Getting contract info...")
            contract_info = self.get_contract_info(checksummed_token)
            total_supply = self.get_total_supply(checksummed_token)
            token_symbol = contract_info['symbol']
            logger.info(f"Token Symbol: {token_symbol}")
            logger.info(f"Total Supply: {total_supply}")
            
            # Get and analyze deployer
            logger.info("\nGetting contract deployer...")
            deployer_address = self.get_contract_deployer(checksummed_token)
            deployer_analysis = None
            if deployer_address:
                logger.info(f"Analyzing deployer: {deployer_address}")
                deployer_analysis = self.analyze_holder(checksummed_token, deployer_address, total_supply)
                if deployer_analysis:
                    deployer_type = self.get_address_type(deployer_address)
                    deployer_analysis["address_type"] = deployer_type
                    logger.info(f"Deployer type: {deployer_type}")
            else:
                logger.warning("Could not find contract deployer")
            
            # Get top holders
            logger.info("\nFetching top holders...")
            top_holders = self.get_top_holders(checksummed_token, self.num_holders)
            logger.info(f"Found {len(top_holders)} holders")
            
            # Analyze each holder
            logger.info("\nAnalyzing holders...")
            holders_analysis = []
            total_holders = len(top_holders)
            
            for idx, holder in enumerate(top_holders, 1):
                logger.info(f"\nProgress: {idx}/{total_holders} ({(idx/total_holders)*100:.1f}%)")
                holder_analysis = self.analyze_holder(checksummed_token, holder, total_supply)
                if holder_analysis:
                    holder_type = self.get_address_type(holder)
                    holder_analysis["address_type"] = holder_type
                    holders_analysis.append(holder_analysis)
                    logger.info(f"Holder {holder[:8]}... analyzed. Type: {holder_type}")
                time.sleep(0.1)  # Rate limiting

            # Perform wallet connection analysis for deep scanning
            connection_analysis = None
            connection_report = None
            if wallet_analyzer and len(holders_analysis) >= 50:
                logger.info("\nAnalyzing wallet connections...")
                try:
                    # Add token address to holder data for report generation
                    for holder in holders_analysis:
                        holder['token_address'] = checksummed_token
                        
                    connection_analysis = wallet_analyzer.analyze_wallet_connections(holders_analysis)
                    if connection_analysis:
                        logger.info(f"Connection analysis completed. Found {len(connection_analysis.get('clusters', []))} clusters")
                        # Find the connection report file
                        report_files = [f for f in os.listdir() if f.startswith(f"connections_report_{checksummed_token}")]
                        if report_files:
                            connection_report = max(report_files, key=os.path.getctime)
                            logger.info(f"Found connection report: {connection_report}")
                except Exception as e:
                    logger.error(f"Error in wallet connection analysis: {str(e)}")
                    connection_analysis = None
            
            # Prepare final analysis results
            analysis_results = {
                "contract_info": contract_info,
                "total_supply": total_supply,
                "deployer_analysis": deployer_analysis,
                "holders_analysis": holders_analysis,
                "connection_analysis": connection_analysis,
                "connection_report": connection_report,  # Add the report file path
                "analysis_type": analysis_type
            }
            
            # Generate CSV reports
            logger.info("\nGenerating CSV reports...")
            current_date = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # Holders report
            holders_file = f"{token_symbol}_holders_{current_date}.csv"
            self.generate_csv_report(analysis_results, holders_file)
            logger.info(f"Holders report generated: {holders_file}")
            
            # Deployer report
            if deployer_analysis:
                deployer_file = f"{token_symbol}_deployer_{current_date}.csv"
                self.generate_deployer_report(analysis_results, deployer_file)
                logger.info(f"Deployer report generated: {deployer_file}")
            
            logger.info(f"Analysis complete for {token_symbol}")
            return analysis_results

        except Exception as e:
            logger.error(f"Error analyzing token: {str(e)}")
            return {
                'error': True,
                'message': f"❌ Error analyzing token: {str(e)}"
            }

    def is_valid_token_contract(self, address: str) -> bool:
        """Check if address is a valid token contract with required methods"""
        try:
            # First check if it's a contract
            if not self.is_contract(address):
                return False
            
            # Try to create contract instance
            token_contract = self.w3_base.eth.contract(address=address, abi=self.erc20_abi)
            
            # Check required ERC20 methods
            try:
                # Check symbol
                symbol = token_contract.functions.symbol().call()
                # Check decimals
                decimals = token_contract.functions.decimals().call()
                # Check balanceOf with zero address
                balance = token_contract.functions.balanceOf(
                    "0x0000000000000000000000000000000000000000"
                ).call()
                
                logger.info(f"Valid token contract found: {symbol} with {decimals} decimals")
                return True
            
            except Exception as e:
                logger.warning(f"Address {address} is a contract but not a valid token: {str(e)}")
                return False
            
        except Exception as e:
            logger.error(f"Error checking token contract: {str(e)}")
            return False

    def generate_deployer_report(self, analysis_results: Dict[str, Any], output_file: str):
        """Generate CSV report for deployer analysis"""
        if analysis_results["deployer_analysis"]:
            deployer_data = analysis_results["deployer_analysis"]
            row = {
                "Address Type": deployer_data["address_type"],
                "Address": deployer_data["address"],
                "Token Balance": deployer_data["token_balance"],
                "% of Total Supply": f"{deployer_data['balance_percentage']:.4f}%",
                "Wallet Age (days)": deployer_data["age_info"]["wallet_age_days"],
                "First Activity": deployer_data["age_info"]["first_activity"],
                "Older than 30d": deployer_data["age_info"]["older_than_30d"],
                "Older than 90d": deployer_data["age_info"]["older_than_90d"],
                "Older than 180d": deployer_data["age_info"]["older_than_180d"],
                "Older than 360d": deployer_data["age_info"]["older_than_360d"],
                "Has Base NFTs": deployer_data["nft_info"]["base_nfts"],
                "Has ETH NFTs": deployer_data["nft_info"]["eth_nfts"],
                "Total Base TX": deployer_data["activity_info"]["base_chain"]["total_tx_display"],
                "Base TX (30d)": deployer_data["activity_info"]["base_chain"]["recent_tx_count"],
                "Total ETH TX": deployer_data["activity_info"]["ethereum"]["total_tx_display"],
                "ETH TX (30d)": deployer_data["activity_info"]["ethereum"]["recent_tx_count"],
                "Total TX Count": deployer_data["activity_info"]["total_tx_display"]
            }
            
            df = pd.DataFrame([row])
            df.to_csv(output_file, index=False)
            print(f"Deployer report generated: {output_file}")
        else:
            print("No deployer data available for report")

    def _get_holders_fallback(self, token_address: str, limit: int = None) -> List[str]:
        """Get holders with Covalent as primary and BaseScan as fallback"""
        
        # Try Covalent API first as it's more real-time
        try:
            url = f"https://api.covalenthq.com/v1/8453/tokens/{token_address}/token_holders/"
            headers = {
                "Authorization": f"Bearer {self.covalent_api_key}"
            }
            params = {
                "page-size": limit or self.num_holders,
                "page-number": 0,
                "quote-currency": "USD"
            }
            
            logger.info("Fetching from Covalent API...")
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()['data']
                holders = []
                
                # Verify balances using RPC for extra accuracy
                token_contract = self.w3_base.eth.contract(address=token_address, abi=self.erc20_abi)
                decimals = token_contract.functions.decimals().call()
                
                for item in data.get('items', []):
                    try:
                        holder_address = self.w3_base.to_checksum_address(item['address'])
                        # Verify with RPC call
                        current_balance = token_contract.functions.balanceOf(holder_address).call()
                        if current_balance > 0:
                            holders.append(holder_address)
                            logger.debug(f"Verified Covalent holder {holder_address[:8]}... "
                                       f"balance={current_balance/(10**decimals)}")
                            
                            if len(holders) >= (limit or self.num_holders):
                                break
                    except Exception as e:
                        logger.error(f"Error verifying Covalent holder: {str(e)}")
                        continue
                
                if holders:
                    logger.info(f"Found {len(holders)} verified holders from Covalent")
                    return holders[:limit or self.num_holders]
        
        except Exception as e:
            logger.error(f"Covalent API error: {str(e)}")

        # Try BaseScan as fallback
        try:
            url = "https://api.basescan.org/api"
            params = {
                'module': 'token',
                'action': 'tokenholderlist',
                'contractaddress': token_address,
                'apikey': self.basescan_api_key,
                'page': 1,
                'offset': (limit or self.num_holders) * 2,  # Get extra to account for outdated data
                'sort': 'desc'
            }
            
            logger.info("Falling back to BaseScan API...")
            response = requests.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                if data['status'] == '1' and data['result']:
                    holders = []
                    token_contract = self.w3_base.eth.contract(address=token_address, abi=self.erc20_abi)
                    decimals = token_contract.functions.decimals().call()
                    
                    for holder_data in data['result']:
                        try:
                            if 'TokenHolderAddress' in holder_data:
                                holder_address = self.w3_base.to_checksum_address(holder_data['TokenHolderAddress'])
                                current_balance = token_contract.functions.balanceOf(holder_address).call()
                                if current_balance > 0:
                                    holders.append(holder_address)
                                    logger.debug(f"Verified BaseScan holder {holder_address[:8]}... "
                                               f"balance={current_balance/(10**decimals)}")
                                    
                                    if len(holders) >= (limit or self.num_holders):
                                        break
                        except Exception as e:
                            logger.error(f"Error verifying BaseScan holder: {str(e)}")
                            continue
                    
                    if holders:
                        logger.info(f"Found {len(holders)} verified holders from BaseScan")
                        return holders[:limit or self.num_holders]
    
        except Exception as e:
            logger.error(f"BaseScan API error: {str(e)}")

        logger.error("All holder fetching methods failed")
        return []

    def _inspect_basescan_response(self, data: Dict) -> None:
        """Helper method to inspect BaseScan API response format"""
        try:
            logger.debug("BaseScan API Response Structure:")
            logger.debug(f"Status: {data.get('status')}")
            logger.debug(f"Message: {data.get('message')}")
            
            if 'result' in data and data['result']:
                sample_holder = data['result'][0]
                logger.debug(f"Sample holder data structure: {sample_holder}")
                logger.debug(f"Available keys: {list(sample_holder.keys())}")
        except Exception as e:
            logger.error(f"Error inspecting BaseScan response: {str(e)}")

def main():
    try:
        # Initialize analyzer with desired number of holders
        print("Initializing TokenAnalyzer...")
        analyzer = TokenAnalyzer(num_holders=10)  # No need to pass API keys anymore
        
        token_address = "0x2584c157b72f58eE1EC1c267f69fAc211B15D33E"
        analysis = analyzer.analyze_token(token_address)
        
        print("\nAnalysis Summary:")
        print(f"Token Symbol: {analysis['contract_info']['symbol']}")
        print(f"Total Holders Analyzed: {len(analysis['holders_analysis'])}")
        
    except Exception as e:
        print(f"\nError in main execution: {str(e)}")
        raise

if __name__ == "__main__":
    main() 