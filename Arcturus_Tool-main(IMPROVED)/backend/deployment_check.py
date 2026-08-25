import os
import sys

def check_setup():
    print("--- OQUAT Deployment Health Check ---")
    
    # 1. Check directories
    folders = ["assets", "services", "templates"]
    for folder in folders:
        if os.path.exists(folder):
            print(f"✅ Folder '{folder}' found.")
        else:
            print(f"❌ Missing folder: '{folder}'")

    # 2. Check Logos
    logos = ["assets/arcturus_logo.png", "assets/tid_logo.png"]
    for logo in logos:
        if os.path.exists(logo):
            print(f"✅ Logo '{logo}' found.")
        else:
            print(f"⚠️ Warning: '{logo}' missing. PPT branding will fail.")

    # 3. Check Template
    template = "templates/inventory_template.pptx"
    if os.path.exists(template):
        print(f"✅ PPT Template found.")
    else:
        print(f"❌ Critical: '{template}' missing.")

if __name__ == "__main__":
    check_setup()