"""
LUMON Subscription Generator
For VLESS XHTTP REALITY and Shadowsocks 2022 (multi‑user)
Reads configuration from /etc/xray/config.json
"""

import re
import json
import base64
import socket
import urllib.parse
import subprocess
from pathlib import Path
from typing import Optional, Dict, List, Any

# ==================== ЧТЕНИЕ КОНФИГА XRAY ====================

class XrayConfigReader:
    def __init__(self, config_path: str = "/etc/xray/config.json"):
        self.config_path = Path(config_path)
        self.config: dict = {}
        self._cached_ip: Optional[str] = None
        self._load()

    def _load(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            except Exception:
                self.config = {}

    def get_inbound_by_tag(self, tag: str) -> dict:
        for inbound in self.config.get('inbounds', []):
            if inbound.get('tag') == tag:
                return inbound
        return {}

    def get_inbound_by_protocol(self, protocol: str) -> dict:
        for inbound in self.config.get('inbounds', []):
            if inbound.get('protocol') == protocol:
                return inbound
        return {}

    def get_external_ip(self) -> str:
        """Возвращает IPv4-адрес сервера.
        Сначала пытается получить локальный IP через hostname -I,
        затем через сокет (определяет IP маршрута по умолчанию),
        затем опрашивает внешние сервисы.
        Результат кешируется после первого успешного получения.
        """
        if self._cached_ip is not None:
            return self._cached_ip

        ip = None

        # 1. Локальный IPv4 через hostname -I
        try:
            result = subprocess.run(['hostname', '-I'], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                candidates = result.stdout.strip().split()
                for addr in candidates:
                    if '.' in addr and ':' not in addr:
                        ip = addr
                        break
        except Exception:
            pass

        # 2. Если не нашли, используем сокетный метод (определяет IP основного интерфейса)
        if not ip:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    # Подключаемся к внешнему DNS, но реального соединения не происходит
                    s.connect(('8.8.8.8', 80))
                    ip = s.getsockname()[0]
            except Exception:
                pass

        # 3. Если всё ещё нет, пробуем внешние сервисы (только если есть curl)
        if not ip:
            try:
                # Проверим наличие curl
                subprocess.run(['curl', '--version'], capture_output=True, timeout=1)
                services = [
                    ['curl', '-4', '-s', 'icanhazip.com'],
                    ['curl', '-4', '-s', 'ifconfig.me'],
                    ['curl', '-4', '-s', 'api.ipify.org']
                ]
                for cmd in services:
                    try:
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                        if result.returncode == 0:
                            candidate = result.stdout.strip()
                            if re.match(r'^\d+\.\d+\.\d+\.\d+$', candidate):
                                ip = candidate
                                break
                    except Exception:
                        continue
            except Exception:
                pass

        # Кешируем результат
        if ip:
            self._cached_ip = ip
        else:
            ip = 'localhost'

        return ip

# ==================== ГЕНЕРАТОР VLESS XHTTP REALITY ====================

class VlessXhttpGenerator:
    """Generate VLESS XHTTP Reality links according to the specified template."""

    def __init__(self, config_path: str = "/etc/xray/config.json"):
        self.reader = XrayConfigReader(config_path)
        # Ищем inbound по тегу "VLESS XHTTP REALITY", если нет – по протоколу 'vless'
        self.inbound = self.reader.get_inbound_by_tag("VLESS XHTTP REALITY")
        if not self.inbound:
            self.inbound = self.reader.get_inbound_by_protocol("vless")

    def get_client_by_email(self, email: str) -> dict:
        """Ищет клиента по email в текущем inbound."""
        if not self.inbound:
            return {}
        clients = self.inbound.get('settings', {}).get('clients', [])
        for client in clients:
            if client.get('email') == email:
                return client
        return {}

    def generate_link_for_email(self, email: str, domain: str = None) -> str:
        # Добавляем проверку, что inbound найден
        if not self.inbound:
            print("ERROR: VLESS inbound not found in config")  # В реальном коде лучше использовать logging
            return ""

        client = self.get_client_by_email(email)
        if not client:
            return ""

        uuid = client.get('id', '')
        port = self.inbound.get('port', 443)
        ip = self.reader.get_external_ip()  # всегда используем реальный IP

        # Reality settings
        stream = self.inbound.get('streamSettings', {})
        reality = stream.get('realitySettings', {})
        pb_key = reality.get('publicKey', '')
        s_id = reality.get('shortIds', [''])[0] if reality.get('shortIds') else ''
        sni = reality.get('serverNames', [''])[0] if reality.get('serverNames') else ''

        # XHTTP settings
        xhttp = stream.get('xhttpSettings', {})
        path = xhttp.get('path', '/')

        params = {
            'type': 'xhttp',
            'encryption': 'none',
            'path': path,
            'host': '',
            'mode': 'stream-one',
            'security': 'reality',
            'pbk': pb_key,
            'fp': 'chrome',
            'sni': sni,
            'sid': s_id,
            'spx': '%2F'
        }

        query = '&'.join([f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items()])
        remark = urllib.parse.quote("VLESS XHTTP REALITY", safe='')

        return f"vless://{uuid}@{ip}:{port}?{query}#{remark}"


# ==================== ГЕНЕРАТОР SHADOWSOCKS 2022 (МУЛЬТИПОЛЬЗОВАТЕЛЬСКИЙ) ====================

class Shadowsocks2022Generator:
    """Generate Shadowsocks 2022 multi‑user links."""

    def __init__(self, config_path: str = "/etc/xray/config.json"):
        self.reader = XrayConfigReader(config_path)
        self.inbound = self.reader.get_inbound_by_tag("SHADOWSOCKS")
        if not self.inbound:
            self.inbound = self.reader.get_inbound_by_protocol("shadowsocks")

    def get_client_by_email(self, email: str) -> Optional[dict]:
        """Ищет клиента по email и обогащает его данными из inbound."""
        if not self.inbound:
            return None

        clients = self.inbound.get('settings', {}).get('clients', [])
        for client in clients:
            if client.get('email') == email:
                # Добавляем к клиенту общие настройки inbound'а
                client_copy = client.copy()  # чтобы не менять оригинал
                client_copy['port'] = self.inbound.get('port')
                client_copy['method'] = self.inbound.get('settings', {}).get('method')
                client_copy['server_password'] = self.inbound.get('settings', {}).get('password')
                return client_copy
        return None

    def generate_link_for_email(self, email: str, domain: str = None) -> str:
        if not self.inbound:
            print("ERROR: Shadowsocks inbound not found in config")
            return ""

        client = self.get_client_by_email(email)
        if not client:
            return ""

        ip = self.reader.get_external_ip()
        port = client.get('port', 443)
        method = client.get('method', '2022-blake3-aes-128-gcm')
        server_pass = client.get('server_password', '')
        user_pass = client.get('password', '')

        # НЕ удаляем '=', оставляем как есть
        password_combined = f"{server_pass}:{user_pass}" if server_pass and user_pass else (server_pass or user_pass)

        # Кодируем ТОЛЬКО method:password (без @ip:port)
        user_part = f"{method}:{password_combined}"

        remark = urllib.parse.quote("SHADOWSOCKS", safe='')
        return f"ss://{user_part}@{ip}:{port}?type=tcp#{remark}"

# ==================== УНИВЕРСАЛЬНАЯ ФУНКЦИЯ ====================

def generate_all_links_for_email(email: str, domain: str = None) -> Dict[str, str]:
    """Generate both VLESS and Shadowsocks links for the given email."""
    links = {}

    vless_gen = VlessXhttpGenerator()
    vless_link = vless_gen.generate_link_for_email(email, domain)
    if vless_link:
        links['vless'] = vless_link

    ss_gen = Shadowsocks2022Generator()
    ss_link = ss_gen.generate_link_for_email(email, domain)
    if ss_link:
        links['shadowsocks'] = ss_link

    return links


# ==================== ГЕНЕРАТОР HTML‑СТРАНИЦЫ ПОДПИСКИ ====================

def generate_html_page(user, domain: str = "") -> str:
    """
    Generates subscription HTML page with cards for VLESS and Shadowsocks.
    :param user: object with 'username', 'uuid', 'sub_token' attributes
    :param domain: server IP or domain (used for subscription URL)
    """
    links = generate_all_links_for_email(user.username, domain)

    # Формируем URL подписки (если есть domain и у пользователя есть uuid/sub_token)
    sub_url = ""
    if domain and hasattr(user, 'uuid') and hasattr(user, 'sub_token'):
        sub_url = f"https://{domain}/sub/{user.uuid}/{user.sub_token}"

    def qr_url(data: str) -> str:
        encoded = urllib.parse.quote(data, safe='')
        return f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={encoded}"

    vless_link = links.get('vless', '')
    vless_qr = qr_url(vless_link) if vless_link else ''

    ss_link = links.get('shadowsocks', '')
    ss_qr = qr_url(ss_link) if ss_link else ''

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LUMON - Subscription</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: #f5f7fa;
            color: #1a1a2e;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            position: relative;
            overflow-x: hidden;
        }}

        /* Background with large numbers */
        .numbers-bg {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: 0;
            overflow: hidden;
        }}

        .number-row {{
            position: absolute;
            width: 100%;
            font-family: 'Courier New', monospace;
            font-size: 32px;
            font-weight: 300;
            color: rgba(74, 88, 102, 0.25);
            white-space: nowrap;
            letter-spacing: 12px;
            opacity: 0;
            animation: flicker 3s ease-in-out infinite;
            animation-fill-mode: forwards;
        }}

        @keyframes flicker {{
            0% {{ opacity: 0; }}
            10% {{ opacity: 0.20; }}
            50% {{ opacity: 0.40; }}
            75%, 100% {{ opacity: 0.25; }}
        }}

        .lang-switch-container {{
            position: fixed;
            top: 25px;
            right: 40px;
            z-index: 100;
        }}

        .lang-switch {{
            background: white;
            border: 1px solid #d0d0d0;
            color: #333;
            padding: 8px 20px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.85em;
            font-weight: 600;
            letter-spacing: 0.5px;
            transition: all 0.2s;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }}

        .lang-switch:hover {{
            background: #f0f0f0;
            border-color: #999;
            transform: translateY(-1px);
            box-shadow: 0 2px 6px rgba(0,0,0,0.1);
        }}

        .header {{
            position: relative;
            z-index: 10;
            padding: 15px 60px;
            text-align: center;
        }}

        .header h1 {{
            font-size: 1.8em;
            font-weight: 600;
            color: #1a1a2e;
            letter-spacing: 2px;
        }}

        .main {{
            position: relative;
            z-index: 10;
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 20px 20px 40px;
            gap: 20px;
            max-width: 700px;
            margin: 0 auto;
            width: 100%;
        }}

        .config-card {{
            background: rgba(255, 255, 255, 0.95);
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.08);
            width: 100%;
            border: 1px solid rgba(232, 232, 232, 0.6);
            animation: slideUp 0.8s ease-out;
            position: relative;
            overflow: hidden;
        }}

        .config-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(90deg, #1a1a2e 0%, #4a90a4 100%);
        }}

        @keyframes slideUp {{
            from {{ opacity: 0; transform: translateY(30px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        .card-header {{
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid #e8e8e8;
        }}

        .card-title {{
            font-size: 1.1em;
            font-weight: 600;
            color: #1a1a2e;
        }}

        .config-box {{
            background: #fafbfc;
            border: 1px solid #d0d0d0;
            border-radius: 8px;
            padding: 12px;
            font-family: 'Courier New', monospace;
            font-size: 0.85em;
            color: #333;
            word-break: break-all;
            margin-bottom: 15px;
            line-height: 1.5;
        }}

        .button-group {{
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }}

        .btn {{
            padding: 8px 16px;
            border-radius: 6px;
            border: none;
            cursor: pointer;
            font-size: 0.85em;
            font-weight: 600;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .btn-copy {{
            background: #1a1a2e;
            color: white;
        }}

        .btn-copy:hover {{
            background: #2d2d44;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(26, 26, 46, 0.2);
        }}

        .btn-qr {{
            background: #4a90a4;
            color: white;
        }}

        .btn-qr:hover {{
            background: #3d7a8c;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(74, 144, 164, 0.3);
        }}

        .btn-github {{
            background: #333;
            color: white;
            text-decoration: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 0.85em;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: all 0.2s;
        }}

        .btn-github:hover {{
            background: #24292e;
            transform: translateY(-1px);
        }}

        .btn-appstore {{
            background: #007aff;
            color: white;
            text-decoration: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 0.85em;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: all 0.2s;
        }}

        .btn-appstore:hover {{
            background: #0056b3;
            transform: translateY(-1px);
        }}

        .btn-googleplay {{
            background: #10b981;
            color: white;
            text-decoration: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 0.85em;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: all 0.2s;
        }}

        .btn-googleplay:hover {{
            background: #059669;
            transform: translateY(-1px);
        }}

        .platform-section {{
            background: rgba(255, 255, 255, 0.95);
            padding: 25px;
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.08);
            width: 100%;
            border: 1px solid rgba(232, 232, 232, 0.6);
            animation: slideUp 0.8s ease-out 0.2s both;
            position: relative;
            overflow: hidden;
        }}

        .platform-section::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(90deg, #1a1a2e 0%, #4a90a4 100%);
        }}

        .platform-section-title {{
            font-size: 1.2em;
            font-weight: 600;
            color: #1a1a2e;
            margin-bottom: 20px;
            padding-bottom: 12px;
            border-bottom: 1px solid #e8e8e8;
        }}

        .platform-accordion {{
            display: flex;
            flex-direction: column;
            gap: 10px;
        }}

        .platform-item {{
            border-radius: 8px;
            overflow: hidden;
        }}

        .platform-header {{
            padding: 14px 18px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-weight: 600;
            font-size: 0.9em;
            transition: all 0.3s;
            color: white;
        }}

        .platform-header:hover {{
            opacity: 0.9;
        }}

        .platform-header i.fa-chevron-up {{
            transition: transform 0.3s;
        }}

        .platform-header.active i.fa-chevron-up {{
            transform: rotate(180deg);
        }}

        .platform-windows {{
            background: #0078d4;
        }}

        .platform-ios {{
            background: #86868b;
        }}

        .platform-android {{
            background: #3ddc84;
            color: #1a1a2e;
        }}

        .platform-linux {{
            background: #fabd2f;
            color: #1a1a2e;
        }}

        .platform-content {{
            display: none;
            padding: 15px;
        }}

        .platform-content.windows {{
            background: rgba(0, 120, 212, 0.08);
        }}

        .platform-content.ios {{
            background: rgba(134, 134, 139, 0.08);
        }}

        .platform-content.android {{
            background: rgba(61, 220, 132, 0.15);
        }}

        .platform-content.linux {{
            background: rgba(250, 189, 47, 0.15);
        }}

        .platform-content.active {{
            display: block;
        }}

        .apps-list {{
            display: flex;
            flex-direction: column;
            gap: 10px;
        }}

        .app-item {{
            background: white;
            border: 1px solid #e8e8e8;
            border-radius: 8px;
            padding: 14px;
            display: flex;
            align-items: center;
            gap: 12px;
            transition: all 0.2s;
        }}

        .app-item:hover {{
            border-color: #4a90a4;
            transform: translateX(4px);
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }}

        .app-icon {{
            width: 36px;
            height: 36px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 1.1em;
            flex-shrink: 0;
        }}

        .app-info {{
            flex: 1;
        }}

        .app-name {{
            font-weight: 600;
            color: #1a1a2e;
            font-size: 0.9em;
        }}

        .recommended-badge {{
            background: #4a90a4;
            color: white;
            font-size: 0.7em;
            padding: 2px 6px;
            border-radius: 4px;
            margin-left: 5px;
        }}

        .modal {{
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
            z-index: 1000;
            align-items: center;
            justify-content: center;
            animation: fadeIn 0.3s;
        }}

        .modal.show {{
            display: flex;
        }}

        @keyframes fadeIn {{
            from {{ opacity: 0; }}
            to {{ opacity: 1; }}
        }}

        .modal-content {{
            background: #ffffff;
            padding: 30px;
            border-radius: 12px;
            max-width: 400px;
            width: 90%;
            animation: slideUp 0.3s;
            text-align: center;
        }}

        .modal-header {{
            font-size: 1.3em;
            margin-bottom: 20px;
            color: #1a1a2e;
            font-weight: 600;
        }}

        .qr-code {{
            background: white;
            padding: 15px;
            border-radius: 8px;
            display: inline-block;
            margin: 20px auto;
            display: flex;
            justify-content: center;
            align-items: center;
        }}

        .qr-code img {{
            width: 200px;
            height: 200px;
        }}

        .modal-close {{
            background: #1a1a2e;
            color: white;
            border: none;
            padding: 10px 30px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 500;
            transition: all 0.2s;
            margin-top: 15px;
        }}

        .modal-close:hover {{
            background: #2d2d44;
        }}

        @media (max-width: 768px) {{
            .lang-switch-container {{
                top: 15px;
                right: 15px;
            }}
            .header {{
                padding: 10px 20px;
            }}
            .header h1 {{
                font-size: 1.3em;
            }}
            .main {{
                padding: 15px 15px 30px;
                gap: 15px;
            }}
            .config-card, .platform-section {{
                padding: 18px;
            }}
            .button-group {{
                flex-direction: column;
            }}
            .btn {{
                width: 100%;
                justify-content: center;
            }}
            .number-row {{
                font-size: 20px;
                letter-spacing: 6px;
            }}
            .platform-header {{
                padding: 12px 14px;
                font-size: 0.85em;
            }}
            .app-item {{
                flex-direction: column;
                text-align: center;
                gap: 10px;
            }}
            .app-info {{
                width: 100%;
            }}
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
        <!-- Subscription URL Card -->
        <div class="config-card">
            <div class="card-header">
                <span class="card-title" data-i18n="subUrl">Subscription URL ★ Recommended</span>
            </div>
            <div class="config-box" id="subUrl">{sub_url}</div>
            <div class="button-group">
                <button class="btn btn-copy" onclick="copyText('subUrl')">
                    <span data-i18n="copy">Copy</span>
                </button>
                <button class="btn btn-qr" onclick="showQR('{qr_url(sub_url)}')">
                    <span data-i18n="qr">QR Code</span>
                </button>
            </div>
        </div>

        <!-- VLESS Card -->
        <div class="config-card">
            <div class="card-header">
                <span class="card-title">VLESS XHTTP REALITY</span>
            </div>
            <div class="config-box" id="vlessLink">{vless_link}</div>
            <div class="button-group">
                <button class="btn btn-copy" onclick="copyText('vlessLink')">
                    <span data-i18n="copy">Copy</span>
                </button>
                <button class="btn btn-qr" onclick="showQR('{vless_qr}')">
                    <span data-i18n="qr">QR Code</span>
                </button>
            </div>
        </div>

        <!-- Shadowsocks Card -->
        <div class="config-card">
            <div class="card-header">
                <span class="card-title">SHADOWSOCKS</span>
            </div>
            <div class="config-box" id="ssLink">{ss_link}</div>
            <div class="button-group">
                <button class="btn btn-copy" onclick="copyText('ssLink')">
                    <span data-i18n="copy">Copy</span>
                </button>
                <button class="btn btn-qr" onclick="showQR('{ss_qr}')">
                    <span data-i18n="qr">QR Code</span>
                </button>
            </div>
        </div>

        <!-- Platform Apps Section -->
        <div class="platform-section">
            <h2 class="platform-section-title" data-i18n="downloadApps">Download App</h2>
            <div class="platform-accordion">
                <!-- Windows -->
                <div class="platform-item">
                    <div class="platform-header platform-windows" onclick="togglePlatform('windows')">
                        <span><i class="fab fa-windows" style="margin-right:0.75rem;"></i><span data-i18n="windows">Windows</span></span>
                        <i class="fas fa-chevron-up"></i>
                    </div>
                    <div class="platform-content windows" id="content-windows">
                        <div class="apps-list">
                            <div class="app-item">
                                <div class="app-icon" style="background:#06b6d4;"><i class="fas fa-shield-alt"></i></div>
                                <div class="app-info"><span class="app-name">Hiddify <span class="recommended-badge" data-i18n="recommended">★</span></span></div>
                                <a href="https://github.com/hiddify/hiddify-next" target="_blank" class="btn btn-github"><i class="fab fa-github"></i><span data-i18n="download">Download</span></a>
                            </div>
                            <div class="app-item">
                                <div class="app-icon" style="background:#0078d4;"><i class="fas fa-bolt"></i></div>
                                <div class="app-info"><span class="app-name">v2rayN</span></div>
                                <a href="https://github.com/2dust/v2rayN" target="_blank" class="btn btn-github"><i class="fab fa-github"></i><span data-i18n="download">Download</span></a>
                            </div>
                            <div class="app-item">
                                <div class="app-icon" style="background:#dc2626;"><i class="fas fa-window-maximize"></i></div>
                                <div class="app-info"><span class="app-name">Mihomo</span></div>
                                <a href="https://github.com/MetaCubeX/mihomo" target="_blank" class="btn btn-github"><i class="fab fa-github"></i><span data-i18n="download">Download</span></a>
                            </div>
                            <div class="app-item">
                                <div class="app-icon" style="background:#f97316;"><i class="fas fa-cube"></i></div>
                                <div class="app-info"><span class="app-name">Sing-Box</span></div>
                                <a href="https://github.com/SagerNet/sing-box" target="_blank" class="btn btn-github"><i class="fab fa-github"></i><span data-i18n="download">Download</span></a>
                            </div>
                            <div class="app-item">
                                <div class="app-icon" style="background:#4b5563;"><i class="fas fa-box"></i></div>
                                <div class="app-info"><span class="app-name">Nekobox</span></div>
                                <a href="https://github.com/MatsuriDayo/nekoray" target="_blank" class="btn btn-github"><i class="fab fa-github"></i><span data-i18n="download">Download</span></a>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- iOS & macOS -->
                <div class="platform-item">
                    <div class="platform-header platform-ios" onclick="togglePlatform('ios')">
                        <span><i class="fab fa-apple" style="margin-right:0.75rem;"></i><span data-i18n="ios">iOS & MAC OS</span></span>
                        <i class="fas fa-chevron-up"></i>
                    </div>
                    <div class="platform-content ios" id="content-ios">
                        <div class="apps-list">
                            <div class="app-item">
                                <div class="app-icon" style="background:#06b6d4;"><i class="fas fa-shield-alt"></i></div>
                                <div class="app-info"><span class="app-name">Hiddify <span class="recommended-badge" data-i18n="recommended">★</span></span></div>
                                <a href="https://github.com/hiddify/hiddify-next" target="_blank" class="btn btn-github"><i class="fab fa-github"></i><span data-i18n="download">Download</span></a>
                            </div>
                            <div class="app-item">
                                <div class="app-icon" style="background:#5ac8fa;"><i class="fas fa-bolt"></i></div>
                                <div class="app-info"><span class="app-name">Egern</span></div>
                                <a href="https://apps.apple.com/us/app/egern/id1616105820" target="_blank" class="btn btn-appstore"><i class="fab fa-apple"></i><span data-i18n="appStore">App Store</span></a>
                            </div>
                            <div class="app-item">
                                <div class="app-icon" style="background:#8b5cf6;"><i class="fas fa-rocket"></i></div>
                                <div class="app-info"><span class="app-name">Shadowrocket</span></div>
                                <a href="https://apps.apple.com/app/shadowrocket/id932747118" target="_blank" class="btn btn-appstore"><i class="fab fa-apple"></i><span data-i18n="appStore">App Store</span></a>
                            </div>
                            <div class="app-item">
                                <div class="app-icon" style="background:#f97316;"><i class="fas fa-cube"></i></div>
                                <div class="app-info"><span class="app-name">sing-box</span></div>
                                <a href="https://github.com/SagerNet/sing-box" target="_blank" class="btn btn-github"><i class="fab fa-github"></i><span data-i18n="download">Download</span></a>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Android -->
                <div class="platform-item">
                    <div class="platform-header platform-android" onclick="togglePlatform('android')">
                        <span><i class="fab fa-android" style="margin-right:0.75rem;"></i><span data-i18n="android">Android</span></span>
                        <i class="fas fa-chevron-up"></i>
                    </div>
                    <div class="platform-content android" id="content-android">
                        <div class="apps-list">
                            <div class="app-item">
                                <div class="app-icon" style="background:#06b6d4;"><i class="fas fa-shield-alt"></i></div>
                                <div class="app-info"><span class="app-name">Hiddify <span class="recommended-badge" data-i18n="recommended">★</span></span></div>
                                <a href="https://github.com/hiddify/hiddify-next" target="_blank" class="btn btn-github"><i class="fab fa-github"></i><span data-i18n="download">Download</span></a>
                            </div>
                            <div class="app-item">
                                <div class="app-icon" style="background:#dc2626;"><i class="fas fa-window-maximize"></i></div>
                                <div class="app-info"><span class="app-name">Mihomo</span></div>
                                <a href="https://github.com/MetaCubeX/mihomo" target="_blank" class="btn btn-github"><i class="fab fa-github"></i><span data-i18n="download">Download</span></a>
                            </div>
                            <div class="app-item">
                                <div class="app-icon" style="background:#4b5563;"><i class="fas fa-box"></i></div>
                                <div class="app-info"><span class="app-name">NekoBox</span></div>
                                <a href="https://github.com/MatsuriDayo/NekoBoxForAndroid" target="_blank" class="btn btn-github"><i class="fab fa-github"></i><span data-i18n="download">Download</span></a>
                            </div>
                            <div class="app-item">
                                <div class="app-icon" style="background:#10b981;"><i class="fab fa-google-play"></i></div>
                                <div class="app-info"><span class="app-name">V2Box</span></div>
                                <a href="https://play.google.com/store/apps/details?id=dev.hexasoftware.v2box" target="_blank" class="btn btn-googleplay"><i class="fab fa-google-play"></i><span data-i18n="playStore">Google Play</span></a>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Linux -->
                <div class="platform-item">
                    <div class="platform-header platform-linux" onclick="togglePlatform('linux')">
                        <span><i class="fab fa-linux" style="margin-right:0.75rem;"></i><span data-i18n="linux">Linux</span></span>
                        <i class="fas fa-chevron-up"></i>
                    </div>
                    <div class="platform-content linux" id="content-linux">
                        <div class="apps-list">
                            <div class="app-item">
                                <div class="app-icon" style="background:#06b6d4;"><i class="fas fa-shield-alt"></i></div>
                                <div class="app-info"><span class="app-name">Hiddify <span class="recommended-badge" data-i18n="recommended">★</span></span></div>
                                <a href="https://github.com/hiddify/hiddify-next" target="_blank" class="btn btn-github"><i class="fab fa-github"></i><span data-i18n="download">Download</span></a>
                            </div>
                            <div class="app-item">
                                <div class="app-icon" style="background:#dc2626;"><i class="fas fa-window-maximize"></i></div>
                                <div class="app-info"><span class="app-name">Mihomo</span></div>
                                <a href="https://github.com/MetaCubeX/mihomo" target="_blank" class="btn btn-github"><i class="fab fa-github"></i><span data-i18n="download">Download</span></a>
                            </div>
                            <div class="app-item">
                                <div class="app-icon" style="background:#f97316;"><i class="fas fa-cube"></i></div>
                                <div class="app-info"><span class="app-name">sing-box</span></div>
                                <a href="https://github.com/SagerNet/sing-box" target="_blank" class="btn btn-github"><i class="fab fa-github"></i><span data-i18n="download">Download</span></a>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </main>

    <!-- QR Modal -->
    <div class="modal" id="qrModal">
        <div class="modal-content">
            <h3 class="modal-header" data-i18n="scanQR">Scan QR Code</h3>
            <div class="qr-code" id="qrCode"></div>
            <br>
            <button class="modal-close" onclick="closeQR()" data-i18n="close">Close</button>
        </div>
    </div>

    <script>
        // Generate background numbers
        function generateNumbers() {{
            const container = document.getElementById('numbersBg');
            const rowCount = 14;
            for (let i = 0; i < rowCount; i++) {{
                const row = document.createElement('div');
                row.className = 'number-row';
                row.style.top = (i * 7.5) + '%';
                row.style.animationDelay = (i * 0.2) + 's';
                let numbers = '';
                for (let j = 0; j < 80; j++) {{
                    numbers += Math.floor(Math.random() * 10) + ' ';
                }}
                row.textContent = numbers;
                container.appendChild(row);
            }}
        }}

        // Platform accordion
        function togglePlatform(platform) {{
            const header = event.currentTarget;
            const content = document.getElementById('content-' + platform);
            header.classList.toggle('active');
            content.classList.toggle('active');
        }}

        // Auto-detect platform
        function detectAndOpenPlatform() {{
            const ua = navigator.userAgent.toLowerCase();
            let platform = 'windows';
            if (/iphone|ipad|ipod|mac/i.test(ua)) platform = 'ios';
            else if (/android/i.test(ua)) platform = 'android';
            else if (/linux/i.test(ua)) platform = 'linux';
            const header = document.querySelector('.platform-' + platform);
            if (header) header.click();
        }}

        // Translations
        const translations = {{
            en: {{
                welcome: 'Welcome, {user.username}',
                subUrl: 'Subscription URL ★ Recommended',
                copy: 'Copy',
                qr: 'QR Code',
                downloadApps: 'Download App',
                windows: 'Windows',
                ios: 'iOS & MAC OS',
                android: 'Android',
                linux: 'Linux',
                recommended: '★',
                download: 'Download',
                appStore: 'App Store',
                playStore: 'Google Play',
                scanQR: 'Scan QR Code',
                close: 'Close',
                copied: 'Copied to clipboard!'
            }},
            ru: {{
                welcome: 'Добро пожаловать, {user.username}',
                subUrl: 'URL подписка ★ Рекомендуется',
                copy: 'Копировать',
                qr: 'QR код',
                downloadApps: 'Скачать приложение',
                windows: 'Windows',
                ios: 'iOS и macOS',
                android: 'Android',
                linux: 'Linux',
                recommended: '★',
                download: 'Скачать',
                appStore: 'App Store',
                playStore: 'Google Play',
                scanQR: 'Сканировать QR код',
                close: 'Закрыть',
                copied: 'Скопировано в буфер!'
            }}
        }};

        let currentLang = localStorage.getItem('lumon_lang') || (navigator.language.startsWith('ru') ? 'ru' : 'en');

        document.addEventListener('DOMContentLoaded', () => {{
            generateNumbers();
            applyLanguage();
            detectAndOpenPlatform();
        }});

        function applyLanguage() {{
            document.documentElement.lang = currentLang;
            updateTexts();
            updateLangButton();
        }}

        function updateTexts() {{
            document.querySelectorAll('[data-i18n]').forEach(el => {{
                const key = el.getAttribute('data-i18n');
                if (translations[currentLang][key]) {{
                    el.textContent = translations[currentLang][key];
                }}
            }});
        }}

        function updateLangButton() {{
            document.getElementById('langBtn').textContent = currentLang === 'ru' ? 'RU' : 'EN';
        }}

        function toggleLanguage() {{
            currentLang = currentLang === 'en' ? 'ru' : 'en';
            localStorage.setItem('lumon_lang', currentLang);
            applyLanguage();
        }}

        // Исправленная функция копирования (без alert)
        function copyText(elementId) {{
            const text = document.getElementById(elementId).textContent;
            navigator.clipboard.writeText(text).catch(() => {{
                prompt('Copy manually:', text);
            }});
        }}

        function showQR(qrUrl) {{
            document.getElementById('qrCode').innerHTML = '<img src="' + qrUrl + '" alt="QR Code">';
            document.getElementById('qrModal').classList.add('show');
        }}

        function closeQR() {{
            document.getElementById('qrModal').classList.remove('show');
        }}

        document.getElementById('qrModal').addEventListener('click', (e) => {{
            if (e.target.id === 'qrModal') closeQR();
        }});
        document.addEventListener('keydown', (e) => {{
            if (e.key === 'Escape') closeQR();
        }});
    </script>
</body>
</html>'''
    return html

# ==================== LEGACY WRAPPERS (опционально) ====================

def generate_vless_link(user, domain: str) -> str:
    gen = VlessXhttpGenerator()
    return gen.generate_link_for_email(user.username, domain)


def generate_shadowsocks_link(user, domain: str) -> str:
    gen = Shadowsocks2022Generator()
    return gen.generate_link_for_email(user.username, domain)


def generate_subscription_list(user, domain: str) -> list:
    links = generate_all_links_for_email(user.username, domain)
    return list(links.values())
