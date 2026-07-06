import os
import sys

# Add backend directory to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'engine.settings')

import django
django.setup()

from transactions.services import DepositService

print("Testing Alchemy Webhook Payload...")
alchemy_payload = {
    "event": {
        "activity": [
            {
                "hash": "0xabc123alchemytest",
                "toAddress": "0xTestAlchemyAddress",
                "value": 1.23,
                "asset": "eth"
            }
        ]
    }
}

try:
    DepositService.process_alchemy_deposit(alchemy_payload)
    print("Alchemy payload processed (no errors, but likely skipped if address not found)")
except Exception as e:
    print(f"Alchemy Error: {e}")

print("Testing Blockcypher Webhook Payload...")
blockcypher_payload = {
    "hash": "blockcyphertest123",
    "confirmations": 2,
    "outputs": [
        {
            "addresses": ["1TestBlockcypherAddress"],
            "value": 100000000  # 1 BTC
        }
    ]
}

try:
    DepositService.process_blockcypher_deposit(blockcypher_payload)
    print("Blockcypher payload processed (no errors, but likely skipped if address not found)")
except Exception as e:
    print(f"Blockcypher Error: {e}")

print("Test complete.")
