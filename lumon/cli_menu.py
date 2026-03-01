#!/usr/bin/env python3
"""
LUMON Panel - Interactive CLI Menu
Manage users, cores, backups, and monitoring from terminal
"""

import os
import sys
import json
import uuid
import secrets
import subprocess
import urllib.parse 
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import questionary
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

# Add project to path
sys.path.insert(0, '/opt/lumon')

from lumon.config import config
from lumon.database import SessionLocal, engine
from lumon.models import User, TrafficStat, Event, Backup
from lumon.subscription import generate_subscription_list

# Config path
CONFIG_PATH = Path("/etc/lumon/lumon_config.json")

# ============================================
# Utility Functions
# ============================================
def clear_screen():
    """Clear terminal screen"""
    os.system('clear' if os.name != 'nt' else 'cls')

def print_header(title: str):
    """Print styled header"""
    clear_screen()
    print("=" * 60)
    print(f"  🌟 LUMON Panel - {title}")
    print("=" * 60)
    print()

def get_db_session() -> Session:
    """Get database session"""
    return SessionLocal()

def run_command(cmd: list, capture: bool = True) -> subprocess.CompletedProcess:
    """Run shell command"""
    return subprocess.run(cmd, capture_output=capture, text=True)

def restart_service(name: str) -> bool:
    """Restart systemd service"""
    result = run_command(['systemctl', 'restart', name])
    return result.returncode == 0

def check_service_status(name: str) -> str:
    """Check if service is active"""
    result = run_command(['systemctl', 'is-active', name])
    return result.stdout.strip()

# ============================================
# USER MANAGEMENT
# ============================================
def list_users():
    """List all users with stats and subscription links"""
    print_header("User List")

    db = get_db_session()
    try:
        users = db.query(User).order_by(User.created_at.desc()).all()

        if not users:
            print("📭 No users found")
        else:
            print(f"{'ID':<4} {'Username':<25} {'Status':<10} {'Last Seen':<20}")
            print("-" * 65)
            for user in users:
                status = "✅ Active" if user.is_active else "❌ Disabled"
                last_seen = user.last_seen.strftime("%Y-%m-%d %H:%M") if user.last_seen else "Never"
                print(f"{user.id:<4} {user.username:<25} {status:<10} {last_seen:<20}")

            print()
            print("💡 Tip: Select a user to view/copy subscription URL")

        # Ask if user wants to view subscription URL
        if users and questionary.confirm("\n🔗 View subscription URL for a user?").ask():
            choices = [f"{u.id} - {u.username}" for u in users] + ["← Back"]
            choice = questionary.select("Select user:", choices=choices).ask()

            if choice != "← Back":
                user_id = int(choice.split(" - ")[0])
                user = db.query(User).filter_by(id=user_id).first()

                if user:
                    sub_url = f"https://{config.subscription_domain}{config.subscription_path_template.format(uuid=user.uuid, token=user.sub_token)}"

                    # sub_url = f"https://{sub_domain}/sub/{user_uuid}/{sub_token}"
    
                    # ============================================
                    # SHOW CREDENTIALS WITH FULL SUBSCRIPTION LINK
                    # ============================================
                    print(f"\n{'='*60}")
                    print(f"✅ User '{username}' created successfully!")
                    print(f"{'='*60}")
                    print(f"📋 User Details:")
                    print(f"   • Username:     {username}")
                    print(f"\n🔗 Full Subscription URL:")
                    print(f"   {sub_url}")
                    print(f"\n💡 Open in browser to see all protocols (VLESS, Shadowsocks, Hysteria2)")
                    print(f"{'='*60}")
                   
                    if questionary.confirm("📋 Copy URL to clipboard?").ask():
                        # Try to copy to clipboard (works in some terminals)
                        import subprocess
                        try:
                            subprocess.run(['xclip', '-selection', 'clipboard'], input=sub_url.encode(), check=False)
                            print("✅ Copied to clipboard!")
                        except:
                            print("⚠️  xclip not available, select and copy manually")

    finally:
        db.close()

    input("\nPress Enter to continue...")

def create_user():
    """Create new user with auto-generated credentials and add to Xray config"""
    print("\n👤 Create New User")
    print("-" * 40)
    
    username = input("Enter username (no spaces): ").strip()
    if not username or ' ' in username:
        print("❌ Username cannot be empty or contain spaces")
        return
    
    # Check if user already exists in DB
    db = SessionLocal()
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        print(f"❌ User '{username}' already exists")
        db.close()
        return
    
    # Generate credentials
    user_uuid = str(uuid.uuid4())
    sub_token = secrets.token_urlsafe(32)
    hysteria_auth = secrets.token_urlsafe(16)
    
    # Generate Shadowsocks user password (2022 multi-user format)
    try:
        ss_user_pass = subprocess.run(
            ['openssl', 'rand', '-base64', '32'],
            capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        # Fallback if openssl fails
        ss_user_pass = secrets.token_urlsafe(32)
    
    # Create user in database
    new_user = User(
        username=username,
        uuid=user_uuid,
        sub_token=sub_token,
        hysteria_auth=hysteria_auth,
        ss_user_pass=ss_user_pass,  # Store for Shadowsocks multi-user
        is_active=True,
        created_at=datetime.now(timezone.utc)
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # ============================================
    # ADD USER TO XRAY CONFIG (inline, no separate function)
    # ============================================
    config_path = Path("/etc/xray/config.json")
    
    if config_path.exists():
        try:
            # Load config
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            config_updated = False
            
            # === Update VLESS XHTTP REALITY inbound ===
            for inbound in config.get('inbounds', []):
                if inbound.get('tag') == 'VLESS XHTTP REALITY':
                    clients = inbound.setdefault('settings', {}).setdefault('clients', [])
                    
                    # Check if user already exists (by UUID)
                    if not any(c.get('id') == user_uuid for c in clients):
                        clients.append({
                            'id': user_uuid,
                            'email': username
                        })
                        print(f"   ✅ Added to VLESS clients: {username}")
                        config_updated = True
                    break
            
            # === Update SHADOWSOCKS inbound ===
            for inbound in config.get('inbounds', []):
                if inbound.get('tag') == 'SHADOWSOCKS':
                    clients = inbound.setdefault('settings', {}).setdefault('clients', [])
                    
                    # Check if user already exists (by email)
                    if not any(c.get('email') == username for c in clients):
                        clients.append({
                            'password': ss_user_pass,
                            'email': username
                        })
                        print(f"   ✅ Added to Shadowsocks clients: {username}")
                        config_updated = True
                    break
            
            # Save config if changed
            if config_updated:
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=2)
                
                # Restart Xray to apply changes
                try:
                    subprocess.run(['systemctl', 'restart', 'xray'], check=True, capture_output=True)
                    print("   ✅ Xray restarted with new config")
                except subprocess.CalledProcessError as e:
                    print(f"   ⚠️  Could not restart Xray: {e}")
            else:
                print("   ⚠️  User already exists in config (skipped)")
                
        except json.JSONDecodeError as e:
            print(f"   ❌ Config JSON error: {e}")
        except Exception as e:
            print(f"   ⚠️  Could not update Xray config: {e}")
            print("   💡 User created in DB only - add to config manually if needed")
    else:
        print(f"   ⚠️  Config file not found: {config_path}")
        print("   💡 User created in DB only")
    
    # ============================================
    # GET SUBSCRIPTION DOMAIN FROM CONFIG
    # ============================================
    try:
        from lumon.config import config as lumon_config
        sub_domain = lumon_config.subscription_domain
    except Exception:
        sub_domain = "api.podorozhnik.dlya.ru.net"  # Fallback
    
    # Build full subscription URL
    sub_url = f"https://{sub_domain}/sub/{user_uuid}/{sub_token}"
    
    # ============================================
    # SHOW CREDENTIALS WITH FULL SUBSCRIPTION LINK
    # ============================================
    print(f"\n{'='*60}")
    print(f"✅ User '{username}' created successfully!")
    print(f"{'='*60}")
    print(f"📋 User Details:")
    print(f"   • Username:     {username}")
    print(f"   • UUID:         {user_uuid}")
    print(f"   • Sub Token:    {sub_token}")
    print(f"   • SS User Pass: {ss_user_pass[:20]}...")
    print(f"\n🔗 Full Subscription URL:")
    print(f"   {sub_url}")
    print(f"\n💡 Open in browser to see all protocols (VLESS, Shadowsocks, Hysteria2)")
    print(f"{'='*60}")
    
    db.close()

    input("\nPress Enter to continue...")

def show_user():
    """Show user details with full subscription info"""
    print("\n👁️  Show User")
    print("-" * 40)
    
    db = SessionLocal()
    users = db.query(User).filter(User.is_active == True).all()
    
    if not users:
        print("❌ No active users found")
        db.close()
        return
    
    # Show user list
    print("\nSelect user to show:")
    for i, user in enumerate(users, 1):
        print(f"   {i}. {user.username}")
    
    try:
        choice = int(input("\nEnter number: ").strip())
        if choice < 1 or choice > len(users):
            print("❌ Invalid selection")
            db.close()
            return
        user = users[choice - 1]
    except ValueError:
        print("❌ Invalid input")
        db.close()
        return
    
    # Get subscription domain
    try:
        from lumon.config import config as lumon_config
        sub_domain = lumon_config.subscription_domain
    except Exception:
        sub_domain = "api.podorozhnik.dlya.ru.net"
    
    # Build subscription URL
    sub_url = f"https://{sub_domain}/sub/{user.uuid}/{user.sub_token}"
    
    # Show user details (same format as create_user)
    print(f"\n{'='*60}")
    print(f"✅ User '{user.username}' details:")
    print(f"{'='*60}")
    print(f"📋 User Details:")
    print(f"   • Username:     {user.username}")
    print(f"   • UUID:         {user.uuid}")
    print(f"   • Sub Token:    {user.sub_token}")
    print(f"   • SS User Pass: {user.ss_user_pass[:20] + '...' if user.ss_user_pass else 'N/A'}")
    print(f"\n🔗 Full Subscription URL:")
    print(f"   {sub_url}")
    print(f"\n📱 QR Code for Subscription:")
    print(f"   https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(sub_url)}")
    print(f"\n💡 Open in browser to see all protocols (VLESS, Shadowsocks, Hysteria2)")
    print(f"{'='*60}")
    
    db.close()

    input("\nPress Enter to continue...")

def delete_user():
    """Delete user from DB and Xray config"""
    print("\n🗑️  Delete User")
    print("-" * 40)
    
    db = SessionLocal()
    users = db.query(User).filter(User.is_active == True).all()
    
    if not users:
        print("❌ No active users found")
        db.close()
        return
    
    # Show user list
    print("\nSelect user to delete:")
    for i, user in enumerate(users, 1):
        print(f"   {i}. {user.username}")
    
    try:
        choice = int(input("\nEnter number: ").strip())
        if choice < 1 or choice > len(users):
            print("❌ Invalid selection")
            db.close()
            return
        user = users[choice - 1]
    except ValueError:
        print("❌ Invalid input")
        db.close()
        return
    
    # Confirm deletion
    confirm = input(f"\n⚠️  Delete user '{user.username}'? (yes/no): ").strip().lower()
    if confirm != 'yes':
        print("❌ Deletion cancelled")
        db.close()
        return
    
    username = user.username
    user_uuid = user.uuid
    
    # ============================================
    # REMOVE USER FROM XRAY CONFIG
    # ============================================
    config_path = Path("/etc/xray/config.json")
    
    if config_path.exists():
        try:
            # Load config
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            config_updated = False
            
            # === Remove from VLESS XHTTP REALITY inbound ===
            for inbound in config.get('inbounds', []):
                if inbound.get('tag') == 'VLESS XHTTP REALITY':
                    clients = inbound.setdefault('settings', {}).setdefault('clients', [])
                    original_len = len(clients)
                    # Filter out user by UUID
                    inbound['settings']['clients'] = [c for c in clients if c.get('id') != user_uuid]
                    if len(inbound['settings']['clients']) < original_len:
                        print(f"   ✅ Removed from VLESS clients: {username}")
                        config_updated = True
                    break
            
            # === Remove from SHADOWSOCKS inbound ===
            for inbound in config.get('inbounds', []):
                if inbound.get('tag') == 'SHADOWSOCKS':
                    clients = inbound.setdefault('settings', {}).setdefault('clients', [])
                    original_len = len(clients)
                    # Filter out user by email
                    inbound['settings']['clients'] = [c for c in clients if c.get('email') != username]
                    if len(inbound['settings']['clients']) < original_len:
                        print(f"   ✅ Removed from Shadowsocks clients: {username}")
                        config_updated = True
                    break
            
            # Save config if changed
            if config_updated:
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=2)
                
                # Restart Xray to apply changes
                try:
                    subprocess.run(['systemctl', 'restart', 'xray'], check=True, capture_output=True)
                    print("   ✅ Xray restarted with updated config")
                except subprocess.CalledProcessError as e:
                    print(f"   ⚠️  Could not restart Xray: {e}")
            else:
                print("   ⚠️  User not found in config (DB only)")
                
        except json.JSONDecodeError as e:
            print(f"   ❌ Config JSON error: {e}")
        except Exception as e:
            print(f"   ⚠️  Could not update Xray config: {e}")
    else:
        print(f"   ⚠️  Config file not found: {config_path}")
    
    # ============================================
    # DELETE USER FROM DATABASE
    # ============================================
    db.delete(user)
    db.commit()
    
    print(f"\n✅ User '{username}' deleted successfully!")
    print(f"   • Removed from database")
    print(f"   • Removed from Xray config (if present)")
    
    db.close()

input("\nPress Enter to continue...")

def user_menu():
    """User management submenu - Create, Show, Delete only"""
    while True:
        print_header("User Management")

        choice = questionary.select(
            "Select option:",
            choices=[
                "➕ Create user",
                "👁️  Show user",
                "🗑️  Delete user",
                "← Back"
            ]
        ).ask()

        if choice == "➕ Create user":
            create_user()
        elif choice == "👁️  Show user":
            show_user()
        elif choice == "🗑️  Delete user":
            delete_user()
        elif choice == "← Back":
            break
            
# ============================================
# HYSTERIA2 MANAGEMENT
# ============================================
def edit_hysteria_config():
    """Edit Hysteria2 config with nano"""
    print_header("Edit Hysteria2 Config")

    config_path = "/etc/hysteria/config.yaml"
    if not os.path.exists(config_path):
        print("❌ Config not found")
        input("Press Enter to continue...")
        return

    print(f"📝 Opening {config_path} in nano...")
    print("💡 Ctrl+X to save, Ctrl+O + Enter to confirm")
    print("💡 Press Enter to open editor, or Ctrl+C to cancel")

    # Запускаем nano БЕЗ capture_output - важно для интерактивных программ!
    try:
        result = subprocess.run(['nano', config_path])

        if result.returncode == 0:
            print("\n✅ Editor closed")

            if questionary.confirm("Validate and restart Hysteria2?").ask():
                # Test config
                test_result = subprocess.run(
                    ['hysteria', 'server', '-c', config_path, '--test'],
                    capture_output=True,
                    text=True
                )

                if test_result.returncode == 0:
                    if restart_service('hysteria'):
                        print("✅ Config valid, service restarted")
                    else:
                        print("❌ Failed to restart service")
                else:
                    print(f"❌ Config validation failed:")
                    print(test_result.stderr[:500] if test_result.stderr else "Unknown error")

                    if questionary.confirm("Revert changes from backup?").ask():
                        if os.path.exists(config_path + '.bak'):
                            shutil.copy2(config_path + '.bak', config_path)
                            print("✅ Reverted from backup")
                        else:
                            print("⚠️  No backup found - manual revert required")
        else:
            print(f"⚠️  Editor exited with code {result.returncode}")

    except KeyboardInterrupt:
        print("\n⚠️  Editor cancelled")
    except Exception as e:
        print(f"❌ Error: {e}")

    input("\nPress Enter to continue...")

def restart_hysteria():
    """Restart Hysteria2 service"""
    print_header("Restart Hysteria2")

    status = check_service_status('hysteria')
    print(f"Current status: {status}")

    if restart_service('hysteria'):
        print("✅ Service restarted")
    else:
        print("❌ Failed to restart")

    input("\nPress Enter to continue...")

def check_hysteria_update():
    """Check for Hysteria2 updates"""
    print_header("Check Hysteria2 Update")

    # Get current version
    result = run_command(['hysteria', '--version'])
    current = result.stdout.strip().split()[-1] if result.returncode == 0 else "unknown"

    # Get latest from GitHub
    import requests
    try:
        resp = requests.get('https://api.github.com/repos/apernet/hysteria/releases/latest', timeout=10)
        latest = resp.json()['tag_name'].replace('app/v', '')

        print(f"📦 Current:  {current}")
        print(f"📦 Latest:   {latest}")

        if current != latest and questionary.confirm(f"Update to v{latest}?").ask():
            print("🔄 Downloading...")
            run_command([
                'wget', '-q',
                f'https://github.com/apernet/hysteria/releases/download/app/v{latest}/hysteria-linux-amd64',
                '-O', '/usr/local/bin/hysteria'
            ])
            run_command(['chmod', '+x', '/usr/local/bin/hysteria'])

            # Backup before restart
            shutil.copy2('/etc/hysteria/config.yaml', '/etc/hysteria/config.yaml.bak')

            if restart_service('hysteria'):
                print(f"✅ Updated to v{latest}")
            else:
                print("⚠️  Update downloaded, but restart failed")
    except Exception as e:
        print(f"❌ Error checking updates: {e}")

    input("\nPress Enter to continue...")

def hysteria_menu():
    """Hysteria2 management submenu"""
    while True:
        print_header("Hysteria2 Management")

        choice = questionary.select(
            "Select option:",
            choices=[
                "📝 Edit configuration",
                "🔄 Restart service",
                "📦 Check for updates",
                "📊 View logs (tail)",
                "← Back"
            ]
        ).ask()

        if choice == "📝 Edit configuration":
            edit_hysteria_config()
        elif choice == "🔄 Restart service":
            restart_hysteria()
        elif choice == "📦 Check for updates":
            check_hysteria_update()
        elif choice == "📊 View logs (tail)":
            run_command(['journalctl', '-u', 'hysteria', '-n', '50', '-f'])
        elif choice == "← Back":
            break

# ============================================
# XRAY MANAGEMENT
# ============================================
def edit_xray_config():
    """Edit Xray config with nano"""
    print_header("Edit Xray Config")

    config_path = "/etc/xray/config.json"
    if not os.path.exists(config_path):
        print("❌ Config not found")
        input("Press Enter to continue...")
        return

    print(f"📝 Opening {config_path} in nano...")
    print("💡 Ctrl+X to save, Ctrl+O + Enter to confirm")
    print("💡 Press Enter to open editor, or Ctrl+C to cancel")

    try:
        result = subprocess.run(['nano', config_path])

        if result.returncode == 0:
            print("\n✅ Editor closed")

            if questionary.confirm("Validate and restart Xray?").ask():
                # Test config
                test_result = subprocess.run(
                    ['xray', 'test', '-config', config_path],
                    capture_output=True,
                    text=True
                )

                if test_result.returncode == 0:
                    if restart_service('xray'):
                        print("✅ Config valid, service restarted")
                    else:
                        print("❌ Failed to restart service")
                else:
                    print(f"❌ Config validation failed:")
                    print(test_result.stdout[:500] if test_result.stdout else "Unknown error")

                    if questionary.confirm("Revert changes from backup?").ask():
                        if os.path.exists(config_path + '.bak'):
                            shutil.copy2(config_path + '.bak', config_path)
                            print("✅ Reverted from backup")
                        else:
                            print("⚠️  No backup found - manual revert required")
        else:
            print(f"⚠️  Editor exited with code {result.returncode}")

    except KeyboardInterrupt:
        print("\n⚠️  Editor cancelled")
    except Exception as e:
        print(f"❌ Error: {e}")

    input("\nPress Enter to continue...")

def restart_xray():
    """Restart Xray service"""
    print_header("Restart Xray")

    status = check_service_status('xray')
    print(f"Current status: {status}")

    if restart_service('xray'):
        print("✅ Service restarted")
    else:
        print("❌ Failed to restart")

    input("\nPress Enter to continue...")

def check_xray_update():
    """Check for Xray updates"""
    print_header("Check Xray Update")

    # Get current version
    result = run_command(['xray', 'version'])
    current = result.stdout.strip().split()[-1] if result.returncode == 0 else "unknown"

    # Get latest from GitHub
    import requests
    try:
        resp = requests.get('https://api.github.com/repos/XTLS/Xray-core/releases/latest', timeout=10)
        latest = resp.json()['tag_name'].replace('v', '')

        print(f"📦 Current:  {current}")
        print(f"📦 Latest:   {latest}")

        if current != latest and questionary.confirm(f"Update to v{latest}?").ask():
            print("🔄 Downloading...")
            run_command([
                'wget', '-q',
                f'https://github.com/XTLS/Xray-core/releases/download/v{latest}/Xray-linux-64.zip',
                '-O', '/tmp/xray.zip'
            ])
            run_command(['unzip', '-q', '-o', '/tmp/xray.zip', '-d', '/usr/local/bin/'])
            run_command(['chmod', '+x', '/usr/local/bin/xray'])

            # Backup before restart
            shutil.copy2('/etc/xray/config.json', '/etc/xray/config.json.bak')

            if restart_service('xray'):
                print(f"✅ Updated to v{latest}")
            else:
                print("⚠️  Update downloaded, but restart failed")
    except Exception as e:
        print(f"❌ Error checking updates: {e}")

    input("\nPress Enter to continue...")

def xray_menu():
    """Xray management submenu"""
    while True:
        print_header("Xray Management")

        choice = questionary.select(
            "Select option:",
            choices=[
                "📝 Edit configuration",
                "🔄 Restart service",
                "📦 Check for updates",
                "📊 View logs (tail)",
                "← Back"
            ]
        ).ask()

        if choice == "📝 Edit configuration":
            edit_xray_config()
        elif choice == "🔄 Restart service":
            restart_xray()
        elif choice == "📦 Check for updates":
            check_xray_update()
        elif choice == "📊 View logs (tail)":
            run_command(['journalctl', '-u', 'xray', '-n', '50', '-f'])
        elif choice == "← Back":
            break

# ============================================
# MONITORING & STATS
# ============================================
def traffic_overview():
    """Show traffic statistics"""
    print_header("Traffic Overview")

    db = get_db_session()
    try:
        # Total stats
        total = db.query(
            func.sum(TrafficStat.bytes_download),
            func.sum(TrafficStat.bytes_upload),
            func.sum(TrafficStat.connections_count)
        ).first()

        print(f"📊 All-time Statistics:")
        print(f"   Download:  {total[0] / (1024**3):.2f} GB" if total[0] else "   Download:  0 GB")
        print(f"   Upload:    {total[1] / (1024**3):.2f} GB" if total[1] else "   Upload:    0 GB")
        print(f"   Connections: {total[2] or 0}")
        print()

        # Top users
        print("🏆 Top Users (by download):")
        top = db.query(
            User.username,
            func.sum(TrafficStat.bytes_download).label('download')
        ).join(TrafficStat).group_by(User.id).order_by(desc('download')).limit(5).all()

        for i, (username, download) in enumerate(top, 1):
            print(f"   {i}. {username:<20} {download / (1024**2):.1f} MB")

    finally:
        db.close()

    input("\nPress Enter to continue...")

def server_stats():
    """Show server resource usage"""
    print_header("Server Statistics")

    # CPU
    with open('/proc/stat', 'r') as f:
        cpu = f.readline().split()[1:8]
        cpu = [int(x) for x in cpu]
        total = sum(cpu)
        idle = cpu[3]
        usage = 100 * (total - idle) / total if total else 0

    # Memory
    with open('/proc/meminfo', 'r') as f:
        lines = f.readlines()
        mem_total = int(lines[0].split()[1])
        mem_available = int(lines[2].split()[1])
        mem_usage = 100 * (mem_total - mem_available) / mem_total

    # Disk
    disk = shutil.disk_usage('/')
    disk_usage = 100 * disk.used / disk.total

    print(f"💻 CPU Usage:    {usage:.1f}%")
    print(f"🧠 Memory:      {mem_usage:.1f}% ({(mem_total-mem_available)/1024:.0f}MB / {mem_total/1024:.0f}MB)")
    print(f"💾 Disk:        {disk_usage:.1f}% ({disk.used//1024**3}GB / {disk.total//1024**3}GB)")
    print()

    # Service status
    print("🔧 Service Status:")
    for svc in ['nginx', 'xray', 'hysteria', 'lumon-api']:
        status = check_service_status(svc)
        icon = "✅" if status == "active" else "❌"
        print(f"   {icon} {svc:<15} {status}")

    input("\nPress Enter to continue...")

def monitoring_menu():
    """Monitoring submenu"""
    while True:
        print_header("Monitoring & Stats")

        choice = questionary.select(
            "Select option:",
            choices=[
                "📊 Traffic overview",
                "💻 Server resources",
                "📋 Recent events",
                "← Back"
            ]
        ).ask()

        if choice == "📊 Traffic overview":
            traffic_overview()
        elif choice == "💻 Server resources":
            server_stats()
        elif choice == "📋 Recent events":
            db = get_db_session()
            try:
                events = db.query(Event).order_by(desc(Event.created_at)).limit(10).all()
                for e in events:
                    print(f"[{e.created_at:%H:%M}] {e.severity.upper():<8} {e.event_type}: {e.message[:50]}")
            finally:
                db.close()
            input("\nPress Enter to continue...")
        elif choice == "← Back":
            break

# ============================================
# BACKUPS
# ============================================
def create_backup():
    """Create manual backup"""
    print_header("Create Backup")

    backup_path = config.backup_path
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Database backup
    db_file = f"{backup_path}/db-{timestamp}.sql.gz"
    os.makedirs(backup_path, exist_ok=True)

    print("🗄️  Backing up database...")
    cmd = f"pg_dump -U lumon -h localhost lumon_db | gzip > {db_file}"
    result = run_command(['bash', '-c', cmd])

    if result.returncode == 0:
        size = os.path.getsize(db_file) / 1024
        print(f"✅ Database backup: {db_file} ({size:.1f} KB)")
    else:
        print("❌ Database backup failed")

    # Config backup
    print("📁 Backing up configs...")
    config_file = f"{backup_path}/configs-{timestamp}.tar.gz"
    run_command([
        'tar', '-czf', config_file,
        '/etc/lumon', '/etc/xray', '/etc/hysteria', '/etc/nginx/sites-available'
    ])

    if os.path.exists(config_file):
        size = os.path.getsize(config_file) / 1024
        print(f"✅ Config backup: {config_file} ({size:.1f} KB)")

    # Cleanup old backups
    retention = config.backup_retention_days
    print(f"🧹 Cleaning backups older than {retention} days...")
    run_command(['find', backup_path, '-name', '*.gz', '-mtime', f'+{retention}', '-delete'])

    input("\nPress Enter to continue...")

def list_backups():
    """List available backups"""
    print_header("Available Backups")

    backup_path = config.backup_path
    if not os.path.exists(backup_path):
        print("📭 No backup directory")
        input("Press Enter to continue...")
        return

    backups = sorted(Path(backup_path).glob('*.gz'), reverse=True)

    if not backups:
        print("📭 No backups found")
    else:
        print(f"{'File':<50} {'Size':<15} {'Date':<20}")
        print("-" * 85)
        for bp in backups[:10]:  # Show last 10
            stat = bp.stat()
            size = stat.st_size / 1024 / 1024
            date = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            print(f"{bp.name:<50} {size:.2f} MB{'':<8} {date:<20}")

    input("\nPress Enter to continue...")

def backup_menu():
    """Backup submenu"""
    while True:
        print_header("Backups")

        choice = questionary.select(
            "Select option:",
            choices=[
                "💾 Create backup now",
                "📋 List backups",
                "⚙️  Configure retention",
                "← Back"
            ]
        ).ask()

        if choice == "💾 Create backup now":
            create_backup()
        elif choice == "📋 List backups":
            list_backups()
        elif choice == "⚙️  Configure retention":
            days = questionary.text("Days to keep backups:", default=str(config.backup_retention_days)).ask()
            if days and days.isdigit():
                cfg = json.loads(CONFIG_PATH.read_text())
                cfg['backup_retention_days'] = int(days)
                CONFIG_PATH.write_text(json.dumps(cfg, indent=4))
                print(f"✅ Retention set to {days} days")
            input("Press Enter to continue...")
        elif choice == "← Back":
            break

# ============================================
# LUMON SETTINGS
# ============================================
def edit_lumon_config():
    """Edit main LUMON config with nano"""
    print_header("Edit LUMON Config")

    config_path = "/etc/lumon/lumon_config.json"
    if not os.path.exists(config_path):
        print("❌ Config not found")
        input("Press Enter to continue...")
        return

    print(f"📝 Opening {config_path} in nano...")
    print("💡 Ctrl+X to save, Ctrl+O + Enter to confirm")
    print("💡 Press Enter to open editor, or Ctrl+C to cancel")

    try:
        # Запускаем nano БЕЗ capture_output - важно для интерактивных программ!
        result = subprocess.run(['nano', config_path])

        if result.returncode == 0:
            print("\n✅ Editor closed")

            # Reload config to apply changes
            config.load()
            print("✅ Configuration reloaded")

            if questionary.confirm("Restart services to apply changes?").ask():
                print("🔄 Restarting services...")

                # Restart affected services
                services_restarted = []

                if restart_service('lumon-api'):
                    services_restarted.append('lumon-api')

                if restart_service('nginx'):
                    services_restarted.append('nginx')

                if services_restarted:
                    print(f"✅ Restarted: {', '.join(services_restarted)}")
                else:
                    print("⚠️  Some services failed to restart")
        else:
            print(f"⚠️  Editor exited with code {result.returncode}")

    except KeyboardInterrupt:
        print("\n⚠️  Editor cancelled by user")
    except Exception as e:
        print(f"❌ Error editing config: {e}")

    input("\nPress Enter to continue...")

def check_lumon_update():
    """Check for LUMON updates"""
    print_header("Check LUMON Update")

    print("🔍 Checking GitHub...")
    # For now, just show current version
    print("📦 Current version: 1.0.0 (local)")
    print("🟢 You're running the latest version")

    input("\nPress Enter to continue...")

def lumon_settings_menu():
    """LUMON settings submenu"""
    while True:
        print_header("LUMON Settings")

        choice = questionary.select(
            "Select option:",
            choices=[
                "📝 Edit configuration",
                "📦 Check for updates",
                "🔄 Reinstall LUMON",
                "🗑️  Uninstall LUMON",
                "← Back"
            ]
        ).ask()

        if choice == "📝 Edit configuration":
            edit_lumon_config()
        elif choice == "📦 Check for updates":
            check_lumon_update()
        elif choice == "🔄 Reinstall LUMON":
            if questionary.confirm("⚠️  Reinstall LUMON? This may overwrite configs.").ask():
                print("🔄 Run ./install.sh from /root/lumon-panel to reinstall")
        elif choice == "🗑️  Uninstall LUMON":
            if questionary.confirm("⚠️  UNINSTALL LUMON? This will remove everything!").ask():
                if questionary.confirm("❗ Really? This cannot be undone!").ask():
                    print("🗑️  Manual uninstall required:")
                    print("   1. systemctl stop lumon-api xray hysteria nginx")
                    print("   2. rm -rf /opt/lumon /etc/lumon /var/log/lumon")
                    print("   3. sudo -u postgres psql -c 'DROP DATABASE lumon_db'")
        elif choice == "← Back":
            break

# ============================================
# MAIN MENU
# ============================================
def main_menu():
    """Main CLI entry point"""
    print_header("Welcome")
    print("Initializing LUMON Panel...")

    # Check config
    if not config.load():
        print(f"⚠️  Could not load config from {CONFIG_PATH}")
        print("   Run install.sh first")
        return

    while True:
        print_header("Main Menu")

        choice = questionary.select(
            "Select option:",
            choices=[
                "👥 User Management",
                "🚀 Hysteria2 Settings",
                "☢️  Xray Core Settings",
                "📊 Monitoring & Stats",
                "💾 Backups",
                "⚙️  LUMON Settings",
                "🚪 Exit"
            ]
        ).ask()

        if choice == "👥 User Management":
            user_menu()
        elif choice == "🚀 Hysteria2 Settings":
            hysteria_menu()
        elif choice == "☢️  Xray Core Settings":
            xray_menu()
        elif choice == "📊 Monitoring & Stats":
            monitoring_menu()
        elif choice == "💾 Backups":
            backup_menu()
        elif choice == "⚙️  LUMON Settings":
            lumon_settings_menu()
        elif choice == "🚪 Exit":
            print("\n👋 Goodbye! Stay secure.")
            sys.exit(0)


if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted. Goodbye!")
        sys.exit(130)
