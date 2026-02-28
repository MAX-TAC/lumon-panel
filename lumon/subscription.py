"""
LUMON Subscription Generator - VLESS XHTTP Reality Only
Config path: /etc/xray/config.json
Keys path: /etc/xray/.keys
"""

import json
import base64
import urllib.parse
import subprocess
from pathlib import Path
from typing import List, Dict, Any


class XrayConfigReader:
    """Read Xray config from /etc/xray/config.json"""

    def __init__(self, config_path: str = "/etc/xray/config.json",
                 keys_path: str = "/etc/xray/.keys"):
        self.config_path = Path(config_path)
        self.keys_path = Path(keys_path)
        self.config: dict = {}
        self.keys: dict = {}
        self._load()

    def _load(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            except Exception:
                self.config = {}

        if self.keys_path.exists():
            try:
                with open(self.keys_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if ':' in line:
                            key, value = line.split(':', 1)
                            self.keys[key.strip()] = value.strip()
            except Exception:
                self.keys = {}

    def get_vless_inbound(self) -> dict:
        for inbound in self.config.get('inbounds', []):
            if inbound.get('protocol') == 'vless':
                return inbound
        return {}

    def get_clients(self) -> List[Dict[str, Any]]:
        inbound = self.get_vless_inbound()
        if not inbound:
            return []
        return inbound.get('settings', {}).get('clients', [])

    def get_client_by_email(self, email: str) -> dict:
        for client in self.get_clients():
            if client.get('email') == email:
                return client
        return {}

    def get_reality_settings(self) -> dict:
        inbound = self.get_vless_inbound()
        if not inbound:
            return {}
        return inbound.get('streamSettings', {}).get('realitySettings', {})

    def get_public_key(self) -> str:
        reality = self.get_reality_settings()
        if reality.get('publicKey'):
            return reality['publicKey']
        for key_name in ['PublicKey', 'publicKey', 'pbk']:
            if self.keys.get(key_name):
                return self.keys[key_name]
        return ''

    def get_short_id(self) -> str:
        reality = self.get_reality_settings()
        short_ids = reality.get('shortIds', [])
        if isinstance(short_ids, list) and short_ids:
            return short_ids[0]
        elif short_ids:
            return str(short_ids)
        for key_name in ['shortsid', 'shortId', 'sid']:
            if self.keys.get(key_name):
                return self.keys[key_name]
        return ''

    def get_server_names(self) -> List[str]:
        reality = self.get_reality_settings()
        return reality.get('serverNames', [])

    def get_port(self) -> int:
        """Get port from config - CRITICAL"""
        inbound = self.get_vless_inbound()
        if inbound:
            port = inbound.get('port')
            return port if port else 443
        return 443

    def get_external_ip(self) -> str:
        try:
            result = subprocess.run(
                ['curl', '-4', '-s', 'icanhazip.com'],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return 'localhost'


class VlessXhttpGenerator:
    """Generate VLESS XHTTP Reality links"""

    def __init__(self, config_path: str = "/etc/xray/config.json",
                 keys_path: str = "/etc/xray/.keys"):
        self.reader = XrayConfigReader(config_path, keys_path)

    def generate_link(self, client: dict, domain: str = None) -> str:
        uuid = client.get('id', '')
        email = client.get('email', 'user')
        port = self.reader.get_port()
        pbk = self.reader.get_public_key()
        sid = self.reader.get_short_id()

        server_names = self.reader.get_server_names()
        sni = server_names[0] if server_names else 'github.com'
        ip = domain or self.reader.get_external_ip()

        params = {
            'security': 'reality',
            'path': '/',
            'host': '',
            'mode': 'auto',
            'sni': sni,
            'fp': 'firefox',
            'pbk': pbk,
            'sid': sid,
            'spx': '/',
            'type': 'xhttp',
            'encryption': 'none'
        }

        query_parts = []
        for key, value in params.items():
            encoded_value = urllib.parse.quote(str(value), safe='')
            query_parts.append(f"{key}={encoded_value}")

        query = '&'.join(query_parts)
        remark = urllib.parse.quote(f"vless-{email}", safe='')

        return f"vless://{uuid}@{ip}:{port}?{query}#{remark}"

    def generate_link_for_email(self, email: str, domain: str = None) -> str:
        client = self.reader.get_client_by_email(email)
        if not client:
            return ""
        return self.generate_link(client, domain)

    def generate_all_links(self, domain: str = None) -> List[str]:
        links = []
        for client in self.reader.get_clients():
            link = self.generate_link(client, domain)
            if link:
                links.append(link)
        return links

    def generate_subscription(self, domain: str = None) -> str:
        links = self.generate_all_links(domain)
        if not links:
            return ""
        return base64.b64encode('\n'.join(links).encode()).decode()

    def get_server_info(self) -> dict:
        return {
            'ip': self.reader.get_external_ip(),
            'port': self.reader.get_port(),
            'sni': self.reader.get_server_names()[0] if self.reader.get_server_names() else '',
            'pbk': self.reader.get_public_key(),
            'sid': self.reader.get_short_id(),
            'clients': self.reader.get_clients()
        }


# ============================================
# Legacy wrappers for main.py
# ============================================

def generate_vless_link(user, domain: str = None) -> str:
    gen = VlessXhttpGenerator()
    client = gen.reader.get_client_by_email(user.username)
    if not client:
        client = {'id': user.uuid, 'email': user.username, 'flow': ''}
    return gen.generate_link(client, domain)


def generate_subscription_list(user, domain: str = None) -> List[str]:
    link = generate_vless_link(user, domain)
    return [link] if link else []


# ============================================
# HTML Page Generator
# ============================================

def generate_html_page(user, domain: str = None) -> str:
    gen = VlessXhttpGenerator()

    vless_link = generate_vless_link(user, domain)
    links = [vless_link] if vless_link else []

    sub_content = '\n'.join(links)
    sub_b64 = base64.b64encode(sub_content.encode()).decode() if sub_content else ''
    vless_qr = base64.b64encode(vless_link.encode()).decode() if vless_link else ''

    sub_url = f"https://{domain}/sub/{user.uuid}/{user.sub_token}" if domain else ''
    server = gen.get_server_info()

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LUMON - Subscription</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f7fa; color: #1a1a2e; min-height: 100vh;
            display: flex; flex-direction: column; position: relative; overflow-x: hidden;
        }}
        .numbers-bg {{
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            pointer-events: none; z-index: 0; overflow: hidden;
        }}
        .number-row {{
            position: absolute; width: 100%;
            font-family: 'Courier New', monospace; font-size: 32px; font-weight: 300;
            color: rgba(74, 88, 102, 0.25); white-space: nowrap; letter-spacing: 12px;
            opacity: 0; animation: flicker 3s ease-in-out infinite; animation-fill-mode: forwards;
        }}
        @keyframes flicker {{
            0% {{ opacity: 0; }} 10% {{ opacity: 0.20; }}
            50% {{ opacity: 0.40; }} 75%, 100% {{ opacity: 0.25; }}
        }}
        .lang-switch-container {{ position: fixed; top: 25px; right: 40px; z-index: 100; }}
        .lang-switch {{
            background: white; border: 1px solid #d0d0d0; color: #333;
            padding: 8px 20px; border-radius: 6px; cursor: pointer;
            font-size: 0.85em; font-weight: 600; transition: all 0.2s;
        }}
        .lang-switch:hover {{ background: #f0f0f0; border-color: #999; transform: translateY(-1px); }}
        .header {{ position: relative; z-index: 10; padding: 15px 60px; text-align: center; }}
        .header h1 {{ font-size: 1.8em; font-weight: 600; color: #1a1a2e; letter-spacing: 2px; }}
        .main {{
            position: relative; z-index: 10; flex: 1; display: flex;
            flex-direction: column; align-items: center; padding: 20px 20px 40px 20px;
            gap: 20px; max-width: 700px; margin: 0 auto; width: 100%;
        }}
        .config-card {{
            background: rgba(255, 255, 255, 0.95); padding: 20px; border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.08); width: 100%;
            border: 1px solid rgba(232, 232, 232, 0.6); animation: slideUp 0.8s ease-out;
            position: relative; overflow: hidden;
        }}
        .config-card::before {{
            content: ''; position: absolute; top: 0; left: 0; right: 0; height: 4px;
            background: linear-gradient(90deg, #1a1a2e 0%, #4a90a4 100%);
        }}
        @keyframes slideUp {{ from {{ opacity: 0; transform: translateY(30px); }} to {{ opacity: 1; transform: translateY(0); }} }}
        .card-header {{ margin-bottom: 15px; padding-bottom: 10px; border-bottom: 1px solid #e8e8e8; }}
        .card-title {{ font-size: 1.1em; font-weight: 600; color: #1a1a2e; }}
        .config-box {{
            background: #fafbfc; border: 1px solid #d0d0d0; border-radius: 8px;
            padding: 12px; font-family: 'Courier New', monospace; font-size: 0.85em;
            color: #333; word-break: break-all; margin-bottom: 15px; line-height: 1.5;
        }}
        .button-group {{ display: flex; gap: 10px; flex-wrap: wrap; }}
        .btn {{
            padding: 8px 16px; border-radius: 6px; border: none; cursor: pointer;
            font-size: 0.85em; font-weight: 600; transition: all 0.2s;
            display: flex; align-items: center; gap: 6px;
        }}
        .btn-copy {{ background: #1a1a2e; color: white; }}
        .btn-copy:hover {{ background: #2d2d44; transform: translateY(-1px); box-shadow: 0 4px 12px rgba(26, 26, 46, 0.2); }}
        .btn-qr {{ background: #4a90a4; color: white; }}
        .btn-qr:hover {{ background: #3d7a8c; transform: translateY(-1px); box-shadow: 0 4px 12px rgba(74, 144, 164, 0.3); }}
        .platform-section {{
            background: rgba(255, 255, 255, 0.95); padding: 25px; border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.08); width: 100%;
            border: 1px solid rgba(232, 232, 232, 0.6); animation: slideUp 0.8s ease-out 0.2s both;
            position: relative; overflow: hidden;
        }}
        .platform-section::before {{
            content: ''; position: absolute; top: 0; left: 0; right: 0; height: 4px;
            background: linear-gradient(90deg, #1a1a2e 0%, #4a90a4 100%);
        }}
        .platform-section-title {{
            font-size: 1.2em; font-weight: 600; color: #1a1a2e;
            margin-bottom: 20px; padding-bottom: 12px; border-bottom: 1px solid #e8e8e8;
        }}
        .platform-accordion {{ display: flex; flex-direction: column; gap: 10px; }}
        .platform-item {{ border-radius: 8px; overflow: hidden; }}
        .platform-header {{
            padding: 14px 18px; cursor: pointer; display: flex;
            justify-content: space-between; align-items: center;
            font-weight: 600; font-size: 0.9em; transition: all 0.3s; color: white;
        }}
        .platform-header:hover {{ opacity: 0.9; }}
        .platform-header i.fa-chevron-up {{ transition: transform 0.3s; }}
        .platform-header.active i.fa-chevron-up {{ transform: rotate(180deg); }}
        .platform-windows {{ background: #0078d4; }}
        .platform-ios {{ background: #86868b; }}
        .platform-android {{ background: #3ddc84; color: #1a1a2e; }}
        .platform-linux {{ background: #fabd2f; color: #1a1a2e; }}
        .platform-content {{ display: none; padding: 15px; }}
        .platform-content.windows {{ background: rgba(0, 120, 212, 0.08); }}
        .platform-content.ios {{ background: rgba(134, 134, 139, 0.08); }}
        .platform-content.android {{ background: rgba(61, 220, 132, 0.15); }}
        .platform-content.linux {{ background: rgba(250, 189, 47, 0.15); }}
        .platform-content.active {{ display: block; }}
        .apps-list {{ display: flex; flex-direction: column; gap: 10px; }}
        .app-item {{
            background: white; border: 1px solid #e8e8e8; border-radius: 8px;
            padding: 14px; display: flex; align-items: center; gap: 12px; transition: all 0.2s;
        }}
        .app-item:hover {{ border-color: #4a90a4; transform: translateX(4px); box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
        .app-icon {{
            width: 36px; height: 36px; border-radius: 8px;
            display: flex; align-items: center; justify-content: center;
            color: white; font-size: 1.1em; flex-shrink: 0;
        }}
        .app-info {{ flex: 1; }}
        .app-name {{ font-weight: 600; color: #1a1a2e; font-size: 0.9em; }}
        .recommended-badge {{
            background: #4a90a4; color: white; font-size: 0.7em;
            padding: 2px 6px; border-radius: 4px; margin-left: 5px;
        }}
        .btn-github {{
            background: #333; color: white; text-decoration: none;
            padding: 8px 16px; border-radius: 6px; font-size: 0.85em;
            font-weight: 600; display: inline-flex; align-items: center; gap: 6px; transition: all 0.2s;
        }}
        .btn-github:hover {{ background: #24292e; transform: translateY(-1px); }}
        .btn-appstore {{
            background: #007aff; color: white; text-decoration: none;
            padding: 8px 16px; border-radius: 6px; font-size: 0.85em;
            font-weight: 600; display: inline-flex; align-items: center; gap: 6px; transition: all 0.2s;
        }}
        .btn-appstore:hover {{ background: #0056b3; transform: translateY(-1px); }}
        .btn-googleplay {{
            background: #10b981; color: white; text-decoration: none;
            padding: 8px 16px; border-radius: 6px; font-size: 0.85em;
            font-weight: 600; display: inline-flex; align-items: center; gap: 6px; transition: all 0.2s;
        }}
        .btn-googleplay:hover {{ background: #059669; transform: translateY(-1px); }}
        .footer {{
            position: relative; z-index: 10; padding: 40px 30px;
            text-align: center; color: #888; font-size: 0.85em;
        }}
        .modal {{
            display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.5); z-index: 1000;
            align-items: center; justify-content: center; animation: fadeIn 0.3s;
        }}
        .modal.show {{ display: flex; }}
        @keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
        .modal-content {{
            background: #ffffff; padding: 30px; border-radius: 12px;
            max-width: 400px; width: 90%; animation: slideUp 0.3s; text-align: center;
        }}
        .modal-header {{ font-size: 1.3em; margin-bottom: 20px; color: #1a1a2e; font-weight: 600; }}
        .qr-code {{
            background: white; padding: 15px; border-radius: 8px;
            display: inline-block; margin: 20px auto;
        }}
        .qr-code img {{ width: 200px; height: 200px; }}
        .modal-close {{
            background: #1a1a2e; color: white; border: none;
            padding: 10px 30px; border-radius: 6px; cursor: pointer;
            font-weight: 500; transition: all 0.2s; margin-top: 15px;
        }}
        .modal-close:hover {{ background: #2d2d44; }}
        @media (max-width: 768px) {{
            .lang-switch-container {{ top: 15px; right: 15px; }}
            .header {{ padding: 10px 20px; }}
            .header h1 {{ font-size: 1.3em; }}
            .main {{ padding: 15px 15px 30px 15px; gap: 15px; }}
            .config-card, .platform-section {{ padding: 18px; }}
            .button-group {{ flex-direction: column; }}
            .btn {{ width: 100%; justify-content: center; }}
            .number-row {{ font-size: 20px; letter-spacing: 6px; }}
            .platform-header {{ padding: 12px 14px; font-size: 0.85em; }}
            .app-item {{ flex-direction: column; text-align: center; gap: 10px; }}
            .app-info {{ width: 100%; }}
        }}
    </style>
</head>
<body>
    <div class="numbers-bg" id="numbersBg"></div>
    <div class="lang-switch-container">
        <button class="lang-switch" onclick="toggleLanguage()" id="langBtn">EN</button>
    </div>
    <header class="header">
        <h1 data-i18n="welcome">Welcome, {user.username}</h1>
    </header>
    <main class="main">
        <div class="config-card">
            <div class="card-header">
                <span class="card-title" data-i18n="subUrl">Subscription URL ★ Recommended</span>
            </div>
            <div class="config-box" id="subUrl">{sub_url}</div>
            <div class="button-group">
                <button class="btn btn-copy" onclick="copyText('subUrl')"><span data-i18n="copy">Copy</span></button>
                <button class="btn btn-qr" onclick="showQR('https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={sub_b64}')"><span data-i18n="qr">QR Code</span></button>
            </div>
        </div>
        <div class="config-card">
            <div class="card-header"><span class="card-title">VLESS XHTTP Reality</span></div>
            <div class="config-box" id="vlessLink">{vless_link}</div>
            <div class="button-group">
                <button class="btn btn-copy" onclick="copyText('vlessLink')"><span data-i18n="copy">Copy</span></button>
                <button class="btn btn-qr" onclick="showQR('https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={vless_qr}')"><span data-i18n="qr">QR Code</span></button>
            </div>
            <div style="margin-top: 15px; font-size: 0.85em; color: #666;">
                <strong>Server:</strong> {server['sni']} | <strong>Port:</strong> {server['port']} | <strong>Transport:</strong> XHTTP + Reality
            </div>
        </div>
        <div class="platform-section">
            <h2 class="platform-section-title" data-i18n="downloadApps">Download App</h2>
            <div class="platform-accordion">
                <div class="platform-item">
                    <div class="platform-header platform-windows" onclick="togglePlatform('windows')">
                        <span><i class="fab fa-windows" style="margin-right:0.75rem;"></i><span data-i18n="windows">Windows</span></span>
                        <i class="fas fa-chevron-up"></i>
                    </div>
                    <div class="platform-content windows" id="content-windows">
                        <div class="apps-list">
                            <div class="app-item"><div class="app-icon" style="background:#06b6d4;"><i class="fas fa-shield-alt"></i></div><div class="app-info"><span class="app-name">Hiddify <span class="recommended-badge" data-i18n="recommended">★</span></span></div><a href="https://github.com/hiddify/hiddify-next" target="_blank" class="btn btn-github"><i class="fab fa-github"></i><span data-i18n="download">Download</span></a></div>
                            <div class="app-item"><div class="app-icon" style="background:#0078d4;"><i class="fas fa-bolt"></i></div><div class="app-info"><span class="app-name">v2rayN</span></div><a href="https://github.com/2dust/v2rayN" target="_blank" class="btn btn-github"><i class="fab fa-github"></i><span data-i18n="download">Download</span></a></div>
                            <div class="app-item"><div class="app-icon" style="background:#dc2626;"><i class="fas fa-window-maximize"></i></div><div class="app-info"><span class="app-name">Mihomo</span></div><a href="https://github.com/MetaCubeX/mihomo" target="_blank" class="btn btn-github"><i class="fab fa-github"></i><span data-i18n="download">Download</span></a></div>
                            <div class="app-item"><div class="app-icon" style="background:#f97316;"><i class="fas fa-cube"></i></div><div class="app-info"><span class="app-name">Sing-Box</span></div><a href="https://github.com/SagerNet/sing-box" target="_blank" class="btn btn-github"><i class="fab fa-github"></i><span data-i18n="download">Download</span></a></div>
                            <div class="app-item"><div class="app-icon" style="background:#4b5563;"><i class="fas fa-box"></i></div><div class="app-info"><span class="app-name">Nekobox</span></div><a href="https://github.com/MatsuriDayo/nekoray" target="_blank" class="btn btn-github"><i class="fab fa-github"></i><span data-i18n="download">Download</span></a></div>
                        </div>
                    </div>
                </div>
                <div class="platform-item">
                    <div class="platform-header platform-ios" onclick="togglePlatform('ios')">
                        <span><i class="fab fa-apple" style="margin-right:0.75rem;"></i><span data-i18n="ios">iOS & MAC OS</span></span>
                        <i class="fas fa-chevron-up"></i>
                    </div>
                    <div class="platform-content ios" id="content-ios">
                        <div class="apps-list">
                            <div class="app-item"><div class="app-icon" style="background:#06b6d4;"><i class="fas fa-shield-alt"></i></div><div class="app-info"><span class="app-name">Hiddify <span class="recommended-badge" data-i18n="recommended">★</span></span></div><a href="https://github.com/hiddify/hiddify-next" target="_blank" class="btn btn-github"><i class="fab fa-github"></i><span data-i18n="download">Download</span></a></div>
                            <div class="app-item"><div class="app-icon" style="background:#5ac8fa;"><i class="fas fa-bolt"></i></div><div class="app-info"><span class="app-name">Egern</span></div><a href="https://apps.apple.com/us/app/egern/id1616105820" target="_blank" class="btn btn-appstore"><i class="fab fa-apple"></i><span data-i18n="appStore">App Store</span></a></div>
                            <div class="app-item"><div class="app-icon" style="background:#8b5cf6;"><i class="fas fa-rocket"></i></div><div class="app-info"><span class="app-name">Shadowrocket</span></div><a href="https://apps.apple.com/app/shadowrocket/id932747118" target="_blank" class="btn btn-appstore"><i class="fab fa-apple"></i><span data-i18n="appStore">App Store</span></a></div>
                            <div class="app-item"><div class="app-icon" style="background:#f97316;"><i class="fas fa-cube"></i></div><div class="app-info"><span class="app-name">sing-box</span></div><a href="https://github.com/SagerNet/sing-box" target="_blank" class="btn btn-github"><i class="fab fa-github"></i><span data-i18n="download">Download</span></a></div>
                        </div>
                    </div>
                </div>
                <div class="platform-item">
                    <div class="platform-header platform-android" onclick="togglePlatform('android')">
                        <span><i class="fab fa-android" style="margin-right:0.75rem;"></i><span data-i18n="android">Android</span></span>
                        <i class="fas fa-chevron-up"></i>
                    </div>
                    <div class="platform-content android" id="content-android">
                        <div class="apps-list">
                            <div class="app-item"><div class="app-icon" style="background:#06b6d4;"><i class="fas fa-shield-alt"></i></div><div class="app-info"><span class="app-name">Hiddify <span class="recommended-badge" data-i18n="recommended">★</span></span></div><a href="https://github.com/hiddify/hiddify-next" target="_blank" class="btn btn-github"><i class="fab fa-github"></i><span data-i18n="download">Download</span></a></div>
                            <div class="app-item"><div class="app-icon" style="background:#dc2626;"><i class="fas fa-window-maximize"></i></div><div class="app-info"><span class="app-name">Mihomo</span></div><a href="https://github.com/MetaCubeX/mihomo" target="_blank" class="btn btn-github"><i class="fab fa-github"></i><span data-i18n="download">Download</span></a></div>
                            <div class="app-item"><div class="app-icon" style="background:#4b5563;"><i class="fas fa-box"></i></div><div class="app-info"><span class="app-name">NekoBox</span></div><a href="https://github.com/MatsuriDayo/NekoBoxForAndroid" target="_blank" class="btn btn-github"><i class="fab fa-github"></i><span data-i18n="download">Download</span></a></div>
                            <div class="app-item"><div class="app-icon" style="background:#10b981;"><i class="fab fa-google-play"></i></div><div class="app-info"><span class="app-name">V2Box</span></div><a href="https://play.google.com/store/apps/details?id=dev.hexasoftware.v2box" target="_blank" class="btn btn-googleplay"><i class="fab fa-google-play"></i><span data-i18n="playStore">Google Play</span></a></div>
                        </div>
                    </div>
                </div>
                <div class="platform-item">
                    <div class="platform-header platform-linux" onclick="togglePlatform('linux')">
                        <span><i class="fab fa-linux" style="margin-right:0.75rem;"></i><span data-i18n="linux">Linux</span></span>
                        <i class="fas fa-chevron-up"></i>
                    </div>
                    <div class="platform-content linux" id="content-linux">
                        <div class="apps-list">
                            <div class="app-item"><div class="app-icon" style="background:#06b6d4;"><i class="fas fa-shield-alt"></i></div><div class="app-info"><span class="app-name">Hiddify <span class="recommended-badge" data-i18n="recommended">★</span></span></div><a href="https://github.com/hiddify/hiddify-next" target="_blank" class="btn btn-github"><i class="fab fa-github"></i><span data-i18n="download">Download</span></a></div>
                            <div class="app-item"><div class="app-icon" style="background:#dc2626;"><i class="fas fa-window-maximize"></i></div><div class="app-info"><span class="app-name">Mihomo</span></div><a href="https://github.com/MetaCubeX/mihomo" target="_blank" class="btn btn-github"><i class="fab fa-github"></i><span data-i18n="download">Download</span></a></div>
                            <div class="app-item"><div class="app-icon" style="background:#f97316;"><i class="fas fa-cube"></i></div><div class="app-info"><span class="app-name">sing-box</span></div><a href="https://github.com/SagerNet/sing-box" target="_blank" class="btn btn-github"><i class="fab fa-github"></i><span data-i18n="download">Download</span></a></div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </main>
    <footer class="footer">
        <div class="footer-text" data-i18n="copyright">© 2024 LUMON Industries. All rights reserved.</div>
    </footer>
    <div class="modal" id="qrModal">
        <div class="modal-content">
            <h3 class="modal-header" data-i18n="scanQR">Scan QR Code</h3>
            <div class="qr-code" id="qrCode"></div>
            <br>
            <button class="modal-close" onclick="closeQR()" data-i18n="close">Close</button>
        </div>
    </div>
    <script>
        function generateNumbers() {{
            const container = document.getElementById('numbersBg');
            const rowCount = 14;
            for (let i = 0; i < rowCount; i++) {{
                const row = document.createElement('div');
                row.className = 'number-row';
                row.style.top = (i * 7.5) + '%';
                row.style.animationDelay = (i * 0.2) + 's';
                let numbers = '';
                for (let j = 0; j < 80; j++) {{ numbers += Math.floor(Math.random() * 10) + ' '; }}
                row.textContent = numbers;
                container.appendChild(row);
            }}
        }}
        function togglePlatform(platform) {{
            const header = event.currentTarget;
            const content = document.getElementById('content-' + platform);
            header.classList.toggle('active');
            content.classList.toggle('active');
        }}
        function detectAndOpenPlatform() {{
            const ua = navigator.userAgent.toLowerCase();
            let platform = 'windows';
            if (/iphone|ipad|ipod|mac/i.test(ua)) platform = 'ios';
            else if (/android/i.test(ua)) platform = 'android';
            else if (/linux/i.test(ua)) platform = 'linux';
            const header = document.querySelector('.platform-' + platform);
            if (header) header.click();
        }}
        const translations = {{
            en: {{ welcome: 'Welcome, {user.username}', subUrl: 'Subscription URL ★ Recommended', copy: 'Copy', qr: 'QR Code', downloadApps: 'Download App', windows: 'Windows', ios: 'iOS & MAC OS', android: 'Android', linux: 'Linux', recommended: '★', download: 'Download', appStore: 'App Store', playStore: 'Google Play', scanQR: 'Scan QR Code', close: 'Close', copied: 'Copied to clipboard!' }},
            ru: {{ welcome: 'Добро пожаловать, {user.username}', subUrl: 'URL подписка ★ Рекомендуется', copy: 'Копировать', qr: 'QR код', downloadApps: 'Скачать приложение', windows: 'Windows', ios: 'iOS и macOS', android: 'Android', linux: 'Linux', recommended: '★', download: 'Скачать', appStore: 'App Store', playStore: 'Google Play', scanQR: 'Сканировать QR код', close: 'Закрыть', copied: 'Скопировано в буфер!' }}
        }};
        let currentLang = localStorage.getItem('lumon_lang') || (navigator.language.startsWith('ru') ? 'ru' : 'en');
        document.addEventListener('DOMContentLoaded', () => {{ generateNumbers(); applyLanguage(); detectAndOpenPlatform(); }});
        function applyLanguage() {{
            document.documentElement.lang = currentLang;
            updateTexts();
            document.getElementById('langBtn').textContent = currentLang === 'ru' ? 'RU' : 'EN';
        }}
        function updateTexts() {{
            document.querySelectorAll('[data-i18n]').forEach(el => {{
                const key = el.getAttribute('data-i18n');
                if (translations[currentLang][key]) el.textContent = translations[currentLang][key];
            }});
        }}
        function toggleLanguage() {{
            currentLang = currentLang === 'en' ? 'ru' : 'en';
            localStorage.setItem('lumon_lang', currentLang);
            applyLanguage();
        }}
        function copyText(id) {{
            const text = document.getElementById(id).textContent;
            navigator.clipboard.writeText(text).then(() => alert(translations[currentLang].copied)).catch(() => prompt('Copy:', text));
        }}
        function showQR(url) {{
            document.getElementById('qrCode').innerHTML = '<img src="' + url + '" alt="QR">';
            document.getElementById('qrModal').classList.add('show');
        }}
        function closeQR() {{ document.getElementById('qrModal').classList.remove('show'); }}
        document.getElementById('qrModal').addEventListener('click', (e) => {{ if (e.target.id === 'qrModal') closeQR(); }});
        document.addEventListener('keydown', (e) => {{ if (e.key === 'Escape') closeQR(); }});
    </script>
</body>
</html>'''

    return html
