# nowpayments_handler.py
import time
import requests
import logging
import asyncio
import aiohttp
from typing import Dict, Optional
from datetime import datetime, timedelta

class NOWPaymentsHandler:
    def __init__(self, api_key: str, db_manager):
        self.api_key = api_key
        self.db_manager = db_manager
        self.base_url = "https://api.nowpayments.io/v1"
        self.logger = logging.getLogger('TokenAnalyzer')
        
        self.credit_packages = {
            'basic': {'credits': 50, 'price_usd': 20},
            'pro': {'credits': 75, 'price_usd': 30},
            'premium': {'credits': 100, 'price_usd': 40}
        }
        
        self.default_currency = 'usdttrc20'
        self.supported_currencies = {'usdttrc20'}

    async def create_payment(self, user_id: int, package_name: str, currency: str = None) -> Optional[Dict]:
        try:
            package = self.credit_packages[package_name]
            currency = currency or self.default_currency
            
            headers = {
                'x-api-key': self.api_key,
                'Content-Type': 'application/json'
            }
            
            payload = {
                'price_amount': package['price_usd'],
                'price_currency': 'usd',
                'pay_currency': currency.lower(),
                'order_id': f'cred_{user_id}_{int(time.time())}'
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/payment",
                    headers=headers,
                    json=payload,
                    timeout=30
                ) as response:
                    response_data = await response.json()
                    
                    if response_data.get('payment_id') and response_data.get('pay_address'):
                        payment_data = {
                            'user_id': user_id,
                            'payment_id': response_data['payment_id'],
                            'package_name': package_name,
                            'credits': package['credits'],
                            'amount_usd': package['price_usd'],
                            'amount_crypto': response_data['pay_amount'],
                            'currency': 'USDT',
                            'status': 'pending',
                            'pay_address': response_data['pay_address'],
                            'network': 'TRC20',
                            'order_id': response_data['order_id'],
                            'expiration': response_data.get('expiration_estimate_date'),
                            'provider_data': response_data
                        }

                        if await self.db_manager.store_payment(payment_data):
                            return payment_data

                    self.logger.error(f"Provider error: {response_data}")
                    return {'error': True, 'message': 'Payment service unavailable'}

        except Exception as e:
            self.logger.error(f"Payment creation error: {str(e)}")
            return {'error': True, 'message': 'Payment service error'}

    async def check_payment_status(self, payment_id: str) -> Optional[str]:
        try:
            headers = {'x-api-key': self.api_key}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/payment/{payment_id}",
                    headers=headers,
                    timeout=30
                ) as response:
                    if response.status != 200:
                        return None
                    payment_data = await response.json()
                    return payment_data.get('payment_status')

        except Exception as e:
            self.logger.error(f"Status check error: {str(e)}")
            return None
