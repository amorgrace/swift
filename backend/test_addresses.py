import os
import sys
import django

# Add the backend dir to sys.path
BASE_DIR = r"c:\Users\USER\Desktop\WORK STATION\PYTHON\swift-folder\swift\backend"
sys.path.append(BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'engine.settings')
django.setup()

from authenticator.models import User
from wallets.services import WalletService

def test():
    # Get any user
    user = User.objects.first()
    if not user:
        print("No users found")
        return
    
    print(f"Testing for user: {user.email}")
    try:
        addresses = WalletService.get_deposit_addresses(user)
        print("Deposit addresses:", addresses)
    except Exception as e:
        print("Error:", str(e))

if __name__ == '__main__':
    test()
