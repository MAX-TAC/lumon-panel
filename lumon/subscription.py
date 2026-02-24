"""
LUMON Subscription Generator
Generates vless://, hysteria2://, and Base64 subscription lists
"""

from lumon.models import User
from typing import List
import json

def generate_vless_link(user: User, domain: str, port: int = 443) -> str:
    """
    Generate VLESS link for Xray Core

    Format: vless://uuid@domain:port?type=ws&path=/xray&security=tls#name
    """
    # VLESS WebSocket configuration
    params = {
        "type": "ws",
        "path": "/xray",  # Should match Xray config
        "security": "tls",
        "sni": domain,
        "host": domain
    }

    # Build query string
    query = "&".join(f"{k}={v}" for k, v in params.items())

    # Build full link
    link = f"vless://{user.uuid}@{domain}:{port}?{query}#LUMON-{user.username}"

    return link


def generate_hysteria2_link(user: User, domain: str, port: int = 443) -> str:
    """
    Generate Hysteria2 link

    Format: hysteria2://auth@domain:port?insecure=0&sni=domain#name
    """
    # Get auth from config or use user's hysteria_auth
    # For simplicity, we use the user's auth string
    auth = user.hysteria_auth

    # Build link
    params = {
        "insecure": "0",
        "sni": domain
    }

    query = "&".join(f"{k}={v}" for k, v in params.items())
    link = f"hysteria2://{auth}@{domain}:{port}?{query}#LUMON-{user.username}"

    return link


def generate_subscription_list(user: User, domain: str) -> List[str]:
    """
    Generate subscription list for proxy clients

    Returns list of config lines (will be Base64 encoded)
    """
    lines = []

    # Add VLESS config
    vless = generate_vless_link(user, domain)
    lines.append(vless)

    # Add Hysteria2 config
    hy2 = generate_hysteria2_link(user, domain)
    lines.append(hy2)

    return lines


def generate_html_page(user: User, domain: str) -> str:
    """
    Generate HTML subscription page for browser

    Shows individual configs with copy buttons and QR codes
    """
    vless_link = generate_vless_link(user, domain)
    hy2_link = generate_hysteria2_link(user, domain)
    sub_url = f"https://{domain}/sub/{user.uuid}/{user.sub_token}"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LUMON Subscription - {user.username}</title>
    <style>
        *{{margin:0;padding:0;box-sizing:border-box}}
        body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#1a1a2e;color:#eee;min-height:100vh;padding:20px}}
        .container{{max-width:600px;margin:0 auto}}
        .header{{text-align:center;margin-bottom:30px}}
        .header h1{{color:#e94560;font-size:2em;margin-bottom:10px}}
        .status{{display:inline-block;padding:5px 15px;border-radius:20px;font-size:0.9em;margin-bottom:20px}}
        .status.active{{background:#27ae60}}
        .card{{background:#16213e;border-radius:10px;padding:20px;margin-bottom:20px;box-shadow:0 5px 20px rgba(0,0,0,0.3)}}
        .card h3{{color:#e94560;margin-bottom:15px;font-size:1.2em}}
        .config-box{{background:#1a1a2e;border:1px solid #0f3460;border-radius:5px;padding:12px;margin-bottom:10px;word-break:break-all;font-family:monospace;font-size:0.85em}}
        .btn{{display:inline-block;padding:8px 16px;border:none;border-radius:5px;cursor:pointer;font-size:0.9em;margin-right:5px;margin-top:5px}}
        .btn-copy{{background:#3498db;color:white}}
        .btn-copy:hover{{background:#2980b9}}
        .btn-qr{{background:#9b59b6;color:white}}
        .btn-qr:hover{{background:#8e44ad}}
        .label{{color:#aaa;font-size:0.85em;margin-bottom:5px}}
        .footer{{text-align:center;color:#666;font-size:0.8em;margin-top:30px}}
        .qr-modal{{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.8);justify-content:center;align-items:center}}
        .qr-modal.active{{display:flex}}
        .qr-content{{background:#16213e;padding:30px;border-radius:10px;text-align:center}}
        .qr-close{{background:#e94560;color:white;border:none;padding:10px 20px;border-radius:5px;cursor:pointer;margin-top:15px}}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔗 LUMON</h1>
            <p>Subscription for {user.username}</p>
            <div class="status active">✅ Active</div>
        </div>

        <div class="card">
            <h3>📋 Subscription Link</h3>
            <p class="label">Import this into Hiddify, v2rayNG, or other clients:</p>
            <div class="config-box">{sub_url}</div>
            <button class="btn btn-copy" onclick="copyText('{sub_url}')">📋 Copy</button>
        </div>

        <div class="card">
            <h3>☢️ Xray (VLESS)</h3>
            <p class="label">Individual config for Xray clients:</p>
            <div class="config-box">{vless_link}</div>
            <button class="btn btn-copy" onclick="copyText('{vless_link}')">📋 Copy</button>
            <button class="btn btn-qr" onclick="showQR('{vless_link}')">📱 QR</button>
        </div>

        <div class="card">
            <h3>🚀 Hysteria2</h3>
            <p class="label">Individual config for Hysteria2 clients:</p>
            <div class="config-box">{hy2_link}</div>
            <button class="btn btn-copy" onclick="copyText('{hy2_link}')">📋 Copy</button>
            <button class="btn btn-qr" onclick="showQR('{hy2_link}')">📱 QR</button>
        </div>

        <div class="card">
            <h3>📱 Recommended Clients</h3>
            <ul style="list-style:none;padding:10px;color:#aaa">
                <li>• iOS: Hiddify, Streisand, Shadowrocket</li>
                <li>• Android: Hiddify, v2rayNG, Hysteria2</li>
                <li>• Windows: Hiddify, NekoBox, v2rayN</li>
                <li>• macOS: Hiddify, V2RayU, ClashX</li>
            </ul>
        </div>

        <div class="footer">
            <p>© 2024 LUMON Industries</p>
        </div>
    </div>

    <div class="qr-modal" id="qrModal" onclick="closeQR()">
        <div class="qr-content" onclick="event.stopPropagation()">
            <h3 style="margin-bottom:15px">Scan QR Code</h3>
            <div id="qrCode" style="background:white;padding:20px;border-radius:10px"></div>
            <button class="qr-close" onclick="closeQR()">Close</button>
        </div>
    </div>

    <script>
        function copyText(text) {{
            navigator.clipboard.writeText(text).then(() => {{
                alert('Copied to clipboard!');
            }}).catch(() => {{
                prompt('Copy manually:', text);
            }});
        }}

        function showQR(text) {{
            // Simple QR code using API
            const qrUrl = 'https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=' + encodeURIComponent(text);
            document.getElementById('qrCode').innerHTML = '<img src="' + qrUrl + '" alt="QR Code" style="width:200px;height:200px">';
            document.getElementById('qrModal').classList.add('active');
        }}

        function closeQR() {{
            document.getElementById('qrModal').classList.remove('active');
        }}
    </script>
</body>
</html>"""

    return html
