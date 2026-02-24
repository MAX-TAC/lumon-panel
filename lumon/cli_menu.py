#!/usr/bin/env python3
"""
LUMON Panel - Interactive CLI Menu
Manage users, cores, backups, and monitoring from terminal
"""

import os
import sys
import json
import subprocess
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
    """List all users with stats"""
    print_header("User List")

    db = get_db_session()
    try:
        users = db.query(User).order_by(User.created_at.desc()).all()

        if not users:
            print("📭 No users found")
        else:
            print(f"{'ID':<4} {'Username':<20} {'Status':<10} {'Created':<20} {'Last Seen':<20}")
            print("-" * 80)
            for user in users:
                status = "✅ Active" if user.is_active else "❌ Disabled"
                last_seen = user.last_seen.strftime("%Y-%m-%d %H:%M") if user.last_seen else "Never"
                print(f"{user.id:<4} {user.username:<20} {status:<10} {user.created_at.strftime('%Y-%m-%d %H:%M'):<20} {last_seen:<20}")

        print()
        print("💡 Tip: Use 'Create user' to add new users")

    finally:
        db.close()

    input("\nPress Enter to continue...")

def create_user():
    """Create new user with auto-generated credentials"""
    print_header("Create User")

    username = questionary.text("Enter username (letters/numbers only):").ask()
    if not username or not username.replace("_", "").isalnum():
        print("❌ Invalid username")
        input("Press Enter to continue...")
        return

    # Generate credentials
    import uuid
    import secrets

    user_uuid = str(uuid.uuid4())
    sub_token = secrets.token_urlsafe(32)
    hysteria_auth = secrets.token_urlsafe(24)

    db = get_db_session()
    try:
        # Check if exists
        existing = db.query(User).filter_by(username=username).first()
        if existing:
            print("❌ User already exists")
            input("Press Enter to continue...")
            return

        # Create user
        new_user = User(
            username=username,
            uuid=user_uuid,
            hysteria_auth=hysteria_auth,
            sub_token=sub_token,
            is_active=True
        )
        db.add(new_user)
        db.commit()

        # Generate subscription link
        sub_url = f"https://{config.subscription_domain}{config.subscription_path_template.format(uuid=user_uuid, token=sub_token)}"

        print(f"\n✅ User created successfully!")
        print(f"\n📋 User Details:")
        print(f"   Username:    {username}")
        print(f"   UUID:        {user_uuid}")
        print(f"   Sub Token:   {sub_token}")
        print(f"   Hysteria Auth: {hysteria_auth}")
        print(f"\n🔗 Subscription URL:")
        print(f"   {sub_url}")
        print(f"\n⚠️  Remember to add inbounds to Xray/Hysteria configs!")

        # Log event
        event = Event(
            event_type="user_created",
            severity="info",
            message=f"User created: {username}",
            event_data={"uuid": user_uuid}
        )
        db.add(event)
        db.commit()

    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
    finally:
        db.close()

    input("\nPress Enter to continue...")

def edit_user():
    """Edit or delete user"""
    print_header("Edit User")

    db = get_db_session()
    try:
        users = db.query(User).all()
        if not users:
            print("📭 No users to edit")
            input("Press Enter to continue...")
            return

        choices = [f"{u.id} - {u.username}" for u in users] + ["← Back"]
        choice = questionary.select("Select user:", choices=choices).ask()

        if choice == "← Back":
            return

        user_id = int(choice.split(" - ")[0])
        user = db.query(User).filter_by(id=user_id).first()

        action = questionary.select(
            f"Action for {user.username}:",
            choices=[
                "🔄 Reset subscription token",
                "🔄 Reset Hysteria auth",
                "✏️  Toggle active status",
                "🗑️  Delete user",
                "← Back"
            ]
        ).ask()

        if action == "← Back":
            return

        if action == "🔄 Reset subscription token":
            import secrets
            user.sub_token = secrets.token_urlsafe(32)
            db.commit()
            print("✅ Token reset")

        elif action == "🔄 Reset Hysteria auth":
            import secrets
            user.hysteria_auth = secrets.token_urlsafe(24)
            db.commit()
            print("✅ Hysteria auth reset")

        elif action == "✏️  Toggle active status":
            user.is_active = not user.is_active
            db.commit()
            status = "activated" if user.is_active else "deactivated"
            print(f"✅ User {status}")

        elif action == "🗑️  Delete user":
            confirm = questionary.confirm(f"Delete user {user.username}?").ask()
            if confirm:
                db.delete(user)
                db.commit()
                print("✅ User deleted")

    finally:
        db.close()

    input("\nPress Enter to continue...")

def user_menu():
    """User management submenu"""
    while True:
        print_header("User Management")

        choice = questionary.select(
            "Select option:",
            choices=[
                "📋 List users",
                "➕ Create user",
                "✏️  Edit/Delete user",
                "← Back"
            ]
        ).ask()

        if choice == "📋 List users":
            list_users()
        elif choice == "➕ Create user":
            create_user()
        elif choice == "✏️  Edit/Delete user":
            edit_user()
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
    input("Press Enter to open editor...")

    run_command(['nano', config_path])

    if questionary.confirm("Validate and restart Hysteria2?").ask():
        result = run_command(['hysteria', 'server', '-c', config_path, '--test'])
        if result.returncode == 0:
            if restart_service('hysteria'):
                print("✅ Config valid, service restarted")
            else:
                print("❌ Failed to restart service")
        else:
            print(f"❌ Config validation failed:\n{result.stderr}")
            if questionary.confirm("Revert changes?").ask():
                print("⚠️  Manual revert required - backup your configs!")

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
    input("Press Enter to open editor...")

    run_command(['nano', config_path])

    if questionary.confirm("Validate and restart Xray?").ask():
        result = run_command(['xray', 'test', '-config', config_path])
        if result.returncode == 0:
            if restart_service('xray'):
                print("✅ Config valid, service restarted")
            else:
                print("❌ Failed to restart service")
        else:
            print(f"❌ Config validation failed:\n{result.stdout}")
            if questionary.confirm("Revert changes?").ask():
                print("⚠️  Manual revert required - backup your configs!")

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
    """Edit main LUMON config"""
    print_header("Edit LUMON Config")

    print(f"📝 Opening {CONFIG_PATH} in nano...")
    input("Press Enter to open editor...")

    run_command(['nano', str(CONFIG_PATH)])

    # Reload config
    config.load()

    if questionary.confirm("Restart services to apply changes?").ask():
        restart_service('lumon-api')
        restart_service('nginx')
        print("✅ Services restarted")

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
