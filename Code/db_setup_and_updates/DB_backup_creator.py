import shutil
import os
from datetime import datetime
import duckdb
import pandas as pd
import numpy as np


# Paths
DB_PATH = r"C:\Users\Lavie\OneDrive\Desktop\מוצאים עבודה\פרוייקטים\Stratify - gamify financial strategy\Data_Storage\stratify.duckdb"
backup_folder = r'C:\Users\Lavie\OneDrive\Desktop\מוצאים עבודה\פרוייקטים\Stratify - gamify financial strategy\Backups'


def create_and_verify_backup():
    # Create backup folder if needed
    os.makedirs(backup_folder, exist_ok=True)

    # Check original DB exists
    if not os.path.exists(DB_PATH):
        print(f"❌ Original DB file not found:\n{DB_PATH}")
        return None

    # Create backup file name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(
        backup_folder,
        f"stratify_backup_{timestamp}.duckdb"
    )

    try:
        # Copy DB file
        shutil.copy2(DB_PATH, backup_path)

        # Verify backup exists
        if not os.path.exists(backup_path):
            print("❌ Backup file was not created.")
            return None

        # Verify file size
        original_size = os.path.getsize(DB_PATH)
        backup_size = os.path.getsize(backup_path)

        if original_size != backup_size:
            print("⚠️ Backup was created, but file sizes do not match.")
            print(f"Original size: {original_size} bytes")
            print(f"Backup size:   {backup_size} bytes")
            print(f"Backup path:\n{backup_path}")
            return None

        print("✅ Backup created and verified successfully!")
        print("\n📁 Backup folder:")
        print(backup_folder)

        print("\n📄 Backup file:")
        print(backup_path)

        print("\n👉 To access it:")
        print("1. Open File Explorer")
        print("2. Paste this path in the address bar:")
        print(backup_folder)
        print("3. Look for this file:")
        print(os.path.basename(backup_path))

        return backup_path

    except Exception as e:
        print(f"❌ Error while creating backup: {e}")
        return None




# backup_file = create_and_verify_backup()