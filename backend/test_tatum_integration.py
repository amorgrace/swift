import os
import django
import json
import hmac
import hashlib
import requests
import time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "engine.settings")
django.setup()

from django.contrib.auth import get_user_model
from wallets.services import WalletService
from wallets.models import NGNWallet

User = get_user_model()
user = User.objects.first()

if not user:
    print("No users found to test with!")
    exit(1)

print(f"Testing with user: {user.email}")
print(f"Initial NGN Balance: {NGNWallet.objects.get(user=user).balance}")

# Test 1: Generate deposit addresses
print("\n--- Test 1: Fetching/Generating Deposit Addresses ---")
addresses = WalletService.get_all_deposit_addresses(user)
print("Generated addresses:", json.dumps(addresses, indent=2))

# Find the BTC address
btc_address = None
if 'btc' in addresses and addresses['btc']:
    btc_address = addresses['btc'][0]['address']

if not btc_address:
    print("Could not find BTC address to simulate deposit.")
    exit(1)

# Test 2: Simulate incoming webhook
print("\n--- Test 2: Simulating Tatum Webhook ---")
payload = {
    "txId": f"test_tx_hash_{int(time.time())}",
    "address": btc_address,
    "amount": "0.005",
    "asset": "BTC",
    "confirmations": 3,
    "blockNumber": 123456
}
payload_bytes = json.dumps(payload).encode()

secret = os.environ.get("TATUM_WEBHOOK_SECRET", "")
signature = hmac.new(
    secret.encode(),
    payload_bytes,
    hashlib.sha256,
).hexdigest()

webhook_url = "http://127.0.0.1:8000/api/webhooks/tatum-deposit/"
print(f"Sending fake deposit webhook to {webhook_url}")
print(f"Payload: {payload}")

try:
    response = requests.post(
        webhook_url,
        data=payload_bytes,
        headers={
            "Content-Type": "application/json",
            "x-payload-hash": signature
        }
    )
    print(f"Response status: {response.status_code}")
    print(f"Response body: {response.text}")
except Exception as e:
    print(f"Failed to send request: {e}")

print(f"\nFinal NGN Balance: {NGNWallet.objects.get(user=user).balance}")
