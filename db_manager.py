from datetime import datetime
from typing import Optional, Dict
from supabase import create_client, Client
import os
from dotenv import load_dotenv
import logging
import asyncio  # Add this import statement
import logging  # Add this import statement
import sqlite3


class DatabaseManager:
    def __init__(self):
        load_dotenv()
        
        # Initialize Supabase client
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        self.logger = logging.getLogger('TokenAnalyzer')
        
        if not supabase_url or not supabase_key:
            raise ValueError("Supabase credentials not found in environment variables")
            
        self.supabase: Client = create_client(supabase_url, supabase_key)
        
    def get_user(self, user_id: int) -> Optional[Dict]:
        try:
            response = self.supabase.table('users').select('*').eq('user_id', user_id).execute()
            
            if response.data and len(response.data) > 0:
                user = response.data[0]
                return {
                    "user_id": user['user_id'],
                    "username": user['username'],
                    "credits": user['credits'],
                    "first_seen": user['first_seen'],
                    "last_active": user['last_active']
                }
            return None
            
        except Exception as e:
            print(f"Error getting user: {str(e)}")
            return None

    def create_user(self, user_id: int, username: str) -> None:
        try:
            now = datetime.now().isoformat()
            self.supabase.table('users').insert({
                'user_id': user_id,
                'username': username,
                'credits': 1,
                'first_seen': now,
                'last_active': now
            }).execute()
            
        except Exception as e:
            print(f"Error creating user: {str(e)}")
            raise

    def update_user_activity(self, user_id: int) -> None:
        try:
            self.supabase.table('users').update({
                'last_active': datetime.now().isoformat()
            }).eq('user_id', user_id).execute()
            
        except Exception as e:
            print(f"Error updating user activity: {str(e)}")
            raise

    def deduct_credits(self, user_id: int, credits_required: int = 1) -> bool:
        try:
            # Get current credits
            response = self.supabase.table('users').select('credits').eq('user_id', user_id).execute()
            
            if not response.data or len(response.data) == 0:
                return False
                    
            current_credits = response.data[0]['credits']
            
            if current_credits >= credits_required:
                # Deduct exact amount of credits needed
                self.supabase.table('users').update({
                    'credits': current_credits - credits_required
                }).eq('user_id', user_id).execute()
                return True
                
            return False
                
        except Exception as e:
            self.logger.error(f"Error deducting credits: {str(e)}")
            return False
                
            


    def log_analysis(self, user_id: int, token_address: str, status: str, result_files: str = None) -> None:
        try:
            self.supabase.table('analysis_history').insert({
                'user_id': user_id,
                'token_address': token_address,
                'timestamp': datetime.now().isoformat(),
                'status': status,
                'result_files': result_files
            }).execute()
            
        except Exception as e:
            print(f"Error logging analysis: {str(e)}")
            raise

# Add these methods to your DatabaseManager class

    async def store_payment(self, payment_data: Dict) -> bool:
        try:
            data = {
                'user_id': payment_data['user_id'],
                'payment_id': payment_data['payment_id'],
                'package_name': payment_data['package_name'],
                'credits': payment_data['credits'],
                'amount_usd': payment_data['amount_usd'],
                'amount_crypto': payment_data['amount_crypto'],
                'currency': payment_data['currency'].lower(),
                'status': 'pending',
                'pay_address': payment_data['pay_address'],
                'network': payment_data.get('network', 'eth'),
                'order_id': payment_data['order_id'],
                'expiration': payment_data.get('expiration'),
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
                'provider_data': payment_data.get('provider_data', {})
            }

            for attempt in range(3):
                try:
                    response = self.supabase.table('payments').insert(data).execute()
                    if response.data:
                        self.logger.info(f"Payment {payment_data['payment_id']} stored successfully")
                        return True
                except Exception as e:
                    if attempt == 2:
                        raise e
                    await asyncio.sleep(1)

            return False

        except Exception as e:
            self.logger.error(f"Failed to store payment {payment_data.get('payment_id')}: {str(e)}")
            return False

    async def get_payment(self, payment_id: str) -> Optional[Dict]:
        """Retrieve payment information"""
        try:
            response = self.supabase.table('payments').select('*').eq('payment_id', payment_id).execute()
            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as e:
            print(f"Error getting payment: {str(e)}")
            return None

    async def update_payment_status(self, payment_id: str, status: str) -> bool:
        try:
            response = self.supabase.table('payments').update({
                'status': status,
                'updated_at': datetime.now().isoformat()
            }).eq('payment_id', payment_id).execute()
            
            return bool(response.data)
        except Exception as e:
            self.logger.error(f"Status update error: {str(e)}")
            return False

    async def add_credits(self, user_id: int, credits: int) -> bool:
        """
        Add credits to user account with retries and transaction safety
        """
        try:
            # Input validation
            if credits <= 0:
                self.logger.error(f"Invalid credit amount: {credits}")
                return False
                
            # Check if user exists
            user_exists = await self._validate_user_exists(user_id)
            if not user_exists:
                self.logger.error(f"User {user_id} not found")
                return False

            # Execute credit addition with retries
            for attempt in range(3):
                try:
                    # Update credits directly
                    response = self.supabase.table('users').update({
                        'credits': self.supabase.table('users')
                        .select('credits')
                        .eq('user_id', user_id)
                        .execute()
                        .data[0]['credits'] + credits,
                        'last_active': datetime.now().isoformat()
                    }).eq('user_id', user_id).execute()

                    if response.data:
                        # Log successful credit addition
                        self.logger.info(f"Added {credits} credits to user {user_id}")
                        return True

                except Exception as e:
                    if attempt == 2:  # Last attempt
                        raise e
                    await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff

            return False

        except Exception as e:
            self.logger.error(f"Credit addition failed for user {user_id}: {str(e)}")
            return False


    async def _validate_user_exists(self, user_id: int) -> bool:
        """Validate user exists in database"""
        try:
            # Get user data directly without await
            response = self.supabase.table('users').select('user_id').eq('user_id', user_id).execute()
            return bool(response.data)
        except Exception as e:
            self.logger.error(f"User validation error: {str(e)}")
            return False
        
    async def _log_credit_transaction(self, user_id: int, amount: int, source: str):
        """Log credit transaction for audit trail"""
        try:
            await self.supabase.table('credit_logs').insert({
                'user_id': user_id,
                'amount': amount,
                'source': source,
                'timestamp': datetime.now().isoformat()
            }).execute()
        except Exception as e:
            self.logger.error(f"Failed to log credit transaction: {str(e)}")

    async def get_user_pending_payment(self, user_id: int) -> Optional[Dict]:
        try:
            response = self.supabase.table('payments').select('''
                payment_id,
                package_name,
                credits,
                amount_crypto,
                currency,
                status,
                network,
                order_id,
                pay_address
            ''').eq('user_id', user_id).eq('status', 'pending').execute()
            
            return response.data[0] if response.data else None
        except Exception as e:
            self.logger.error(f"Error getting pending payment: {str(e)}")
            return None

    def use_credit(self, user_id: int, amount: int = 1) -> bool:
        """Deduct credits from user account"""
        try:
            # Get current credits
            response = self.supabase.table('users').select('credits').eq('user_id', user_id).execute()
            
            if not response.data or len(response.data) == 0:
                return False
                
            current_credits = response.data[0]['credits']
            
            if current_credits >= amount:
                # Deduct exact amount of credits needed
                self.supabase.table('users').update({
                    'credits': current_credits - amount,
                    'last_active': datetime.now().isoformat()
                }).eq('user_id', user_id).execute()
                
                # No need to log credit deduction for now
                # We can add credit_logs table later if needed
                
                return True
                
            return False
                
        except Exception as e:
            self.logger.error(f"Error deducting credits: {str(e)}")
            return False