#!/usr/bin/env python3
"""
Reset admin user with optimized bcrypt settings.
Run this script to fix slow login issues.
"""

import bcrypt

# Create new hash with rounds=10 (faster, still secure)
password = "admin123"
salt = bcrypt.gensalt(rounds=10)
password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)

print("New admin password hash (rounds=10):")
print(password_hash.decode('utf-8'))
print("\nVerifying hash works...")

# Test verification
if bcrypt.checkpw(password.encode('utf-8'), password_hash):
    print("✓ Hash verification successful!")
else:
    print("✗ Hash verification failed!")

print("\nRestart your backend server to apply the fix.")
print("The auth manager will recreate the admin user with the optimized settings.")
