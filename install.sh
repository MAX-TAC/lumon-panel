#!/bin/bash
# LUMON Panel Installation Script v1.0
# Ubuntu 24.04 | PostgreSQL 17 | Nginx | Xray | Hysteria2

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[✓]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[!]${NC} $1"; }
log_error() { echo -e "${RED}[✗]${NC} $1"; }

# Check root
if [ "$EUID" -ne 0 ]; then
    log_error "Please run as root: sudo ./install.sh"
    exit 1
fi

log_info "🚀 Starting LUMON Panel installation..."

# ============================================
# STEP 1: System Update & Dependencies
# ============================================
log_info "📦 Step 1/9: Updating system..."
apt update && apt upgrade -y
apt install -y nginx postgresql postgresql-contrib python3-pip python3-venv \
    python3-dev libpq-dev curl wget unzip nano jq openssl cron \
    certbot python3-certbot-nginx logrotate -y
log_success "Dependencies installed"

# ============================================
# STEP 2: PostgreSQL Setup (Ubuntu 24.04 compatible)
# ============================================
log_info "🐘 Step 2/9: Setting up PostgreSQL..."

# Ubuntu 24.04 has PostgreSQL 16 in default repos (fully compatible)
apt install -y postgresql postgresql-contrib

systemctl enable postgresql
systemctl start postgresql

# Generate secure password
DB_PASSWORD=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32)

# Create DB and user (idempotent - safe to re-run)
sudo -u postgres psql -c "SELECT 1 FROM pg_roles WHERE rolname='lumon'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE USER lumon WITH PASSWORD '${DB_PASSWORD}';"

sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw lumon_db || \
    sudo -u postgres psql -c "CREATE DATABASE lumon_db OWNER lumon;"

sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE lumon_db TO lumon;"
sudo -u postgres psql -d lumon_db -c "GRANT ALL ON SCHEMA public TO lumon;"

log_success "PostgreSQL configured"

# ============================================
# STEP 3: Domain Configuration
# ============================================
log_info "🌐 Step 3/9: Domain configuration..."
echo ""
echo "Enter domains (without https://):"
read -p "📡 Subscription domain (e.g., cdn.example.com): " SUB_DOMAIN
read -p "🎭 Decoy domain (e.g., portal.example.com): " DECOY_DOMAIN
read -p "📧 Email for Let's Encrypt (optional): " LETSENCRYPT_EMAIL

if [ -z "$SUB_DOMAIN" ] || [ -z "$DECOY_DOMAIN" ]; then
    log_error "Domains cannot be empty!"
    exit 1
fi

mkdir -p /etc/lumon

# Save config
cat > /etc/lumon/lumon_config.json << EOF
{
    "subscription_domain": "${SUB_DOMAIN}",
    "decoy_domain": "${DECOY_DOMAIN}",
    "subscription_path_template": "/sub/{uuid}/{token}",
    "decoy_path": "/var/www/decoy",
    "db_password": "${DB_PASSWORD}",
    "log_path": "/var/log/lumon",
    "backup_path": "/var/backups/lumon",
    "backup_retention_days": 7,
    "enable_ip_logging": true,
    "enable_rate_limiting": false,
    "install_date": "$(date -Iseconds)"
}
EOF
chmod 600 /etc/lumon/lumon_config.json

log_success "Configuration saved to /etc/lumon/lumon_config.json"

# ============================================
# STEP 4: Logging Setup
# ============================================
log_info "📝 Step 4/9: Setting up logging..."
mkdir -p /var/log/lumon
touch /var/log/lumon/{lumon.log,xray.log,hysteria.log,api.log,backup.log}
chmod 640 /var/log/lumon/*
chown root:adm /var/log/lumon/*
log_success "Logging configured at /var/log/lumon/"

# ============================================
# STEP 5: Install Xray Core
# ============================================
log_info "☢️ Step 5/9: Installing Xray Core..."

# Create directories
mkdir -p /etc/xray
mkdir -p /var/log/lumon
touch /var/log/lumon/xray.log
chmod 640 /var/log/lumon/xray.log

# Get latest version
XRAY_VERSION=$(curl -s https://api.github.com/repos/XTLS/Xray-core/releases/latest | jq -r .tag_name | sed 's/v//')
log_info "Latest Xray version: ${XRAY_VERSION}"

# Download and install
wget -q https://github.com/XTLS/Xray-core/releases/download/v${XRAY_VERSION}/Xray-linux-64.zip -O /tmp/xray.zip
unzip -q -o /tmp/xray.zip -d /usr/local/bin/
chmod +x /usr/local/bin/xray
rm /tmp/xray.zip

# ============================================
# Xray Configuration Setup - AUTO KEY GENERATION
# ============================================
log_info "🔧 Configuring Xray..."

# Generate Reality keys automatically with xray x25519
log_info "🔑 Generating Reality keys..."
xray_keys=$(xray x25519)

# Parse xray x25519 output (Password = public key for Reality)
pr_key=$(echo "$xray_keys" | awk -F': ' '/PrivateKey/ {print $2}' | tr -d '[:space:]')
pb_key=$(echo "$xray_keys" | awk -F': ' '/Password/ {print $2}' | tr -d '[:space:]')

# Generate shortId with openssl
s_id=$(openssl rand -hex 8)

# Generate Shadowsocks password (2022-blake3-aes-128-gcm key)
SS_pass=$(openssl rand -hex 16)

# Save keys to .keys file for subscription.py
cat > /etc/xray/.keys << EOF
PrivateKey: $pr_key
Password: $pb_key
shortsid: $s_id
SS_pass: $SS_pass
EOF
chmod 600 /etc/xray/.keys

log_success "Keys generated and saved to /etc/xray/.keys"

# Request SNI and path from user
echo ""
log_info "🌐 Reality Settings:"
echo "-------------------"

# SNI domain
while true; do
    read -p "Enter SNI domain for Reality masking (e.g., github): " SNI
    if [[ -n "$SNI" && ! "$SNI" =~ [[:space:]] ]]; then
        break
    fi
    log_error "Invalid domain. Try again."
done

# Path for xhttp
while true; do
    read -p "Enter path for XHTTP (e.g., / or /api): " path
    if [[ "$path" =~ ^/ ]]; then
        break
    fi
    log_error "Path must start with /. Try again."
done

# Request Shadowsocks port with recommendations
echo ""
log_info "🔐 Shadowsocks Settings:"
echo "-------------------"
log_info "Recommended ports: 8443, 2083, 2087, 2096, 8880 (avoid 443, 80, 22, 53)"

while true; do
    read -p "Enter port for Shadowsocks (e.g., 8443): " SS_port
    if [[ "$SS_port" =~ ^[0-9]+$ ]] && (( SS_port >= 1024 && SS_port <= 65535 )); then
        if ! ss -tlnp | grep -q ":${SS_port} "; then
            break
        else
            log_warning "Port $SS_port is already in use. Try another."
        fi
    else
        log_error "Port must be a number between 1024-65535. Try again."
    fi
done

log_success "Shadowsocks port: $SS_port"

# Create Xray config with generated keys and user values
log_info "📝 Creating /etc/xray/config.json..."

cat > /etc/xray/config.json << EOF
{
  "log": {
    "access": "/var/log/lumon/xray.log",
    "dnsLog": false,
    "error": "/var/log/lumon/xray.log",
    "loglevel": "warning"
  },
  "routing": {
    "domainStrategy": "AsIs",
    "rules": [
      {
        "type": "field",
        "outboundTag": "blocked",
        "ip": [
          "geoip:private"
        ]
      },
      {
        "type": "field",
        "outboundTag": "blocked",
        "protocol": [
          "bittorrent"
        ]
      }
    ]
  },
  "dns": {
    "servers": [
      "https://8.8.8.8/dns-query",
      "https://dns.cloudflare.com/dns-query",
      "https://dns.quad9.net/dns-query"
    ],
    "queryStrategy": "UseIP",
    "tag": "DNS",
    "enableParallelQuery": true
  },
  "inbounds": [
    {
      "tag": "VLESS XHTTP REALITY",
      "listen": "0.0.0.0",
      "port": 4433,
      "protocol": "vless",
      "settings": {
        "clients": [],
        "decryption": "none",
        "encryption": "none"
      },
      "streamSettings": {
        "network": "xhttp",
        "realitySettings": {
          "maxClientVer": "",
          "maxTimediff": 0,
          "minClientVer": "",
          "mldsa65Seed": "",
          "privateKey": "$pr_key",
          "publicKey": "$pb_key",
          "serverNames": [
            "www.$SNI",
            "$SNI"
          ],
          "shortIds": [
            "$s_id"
          ],
          "show": false,
          "target": "$SNI:443",
          "xver": 0
        },
        "security": "reality",
        "xhttpSettings": {
          "mode": "stream-one",
          "noSSEHeader": false,
          "path": "$path",
          "scMaxBufferedPosts": 30,
          "scMaxEachPostBytes": "1000000",
          "scStreamUpServerSecs": "20-80",
          "xPaddingBytes": "100-1000",
          "xPaddingObfsMode": false
        }
      },
      "sniffing": {
        "enabled": true,
        "destOverride": [
          "http",
          "tls",
          "quic"
        ],
        "metadataOnly": false,
        "routeOnly": false
      }
    },
    {
      "tag": "SHADOWSOCKS",
      "listen": "0.0.0.0",
      "port": $SS_port,
      "protocol": "shadowsocks",
      "settings": {
        "method": "2022-blake3-aes-128-gcm",
        "password": "$SS_pass",
        "network": "tcp,udp",
        "clients": []
      }
    }
  ],
  "outbounds": [
    {
      "tag": "direct",
      "protocol": "freedom",
      "settings": {
        "domainStrategy": "AsIs",
        "redirect": "",
        "noises": []
      }
    },
    {
      "tag": "blocked",
      "protocol": "blackhole",
      "settings": {}
    }
  ],
  "transport": null,
  "policy": {
    "levels": {
      "0": {
        "statsUserDownlink": true,
        "statsUserUplink": true
      }
    },
    "system": {
      "statsInboundDownlink": false,
      "statsInboundUplink": false,
      "statsOutboundDownlink": false,
      "statsOutboundUplink": false
    }
  }
}
EOF

# Set correct permissions
chmod 644 /etc/xray/config.json

# Validate config (optional)
if xray test -config /etc/xray/config.json &>/dev/null; then
    log_success "Config validated"
else
    log_warning "Config validation warning (may still work)"
fi

# Create systemd service
cat > /etc/systemd/system/xray.service << 'EOF'
[Unit]
Description=Xray Core Service
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/xray run -config /etc/xray/config.json
Restart=on-failure
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

# Restart Xray to apply config
systemctl daemon-reload
systemctl enable xray
systemctl restart xray
sleep 2

if systemctl is-active --quiet xray; then
    log_success "Xray Core v${XRAY_VERSION} installed and running"
else
    log_error "Xray failed to start!"
    log_info "Check logs: journalctl -u xray -n 20"
fi

# Show summary (NO link generation - links are generated by subscription.py per user)
echo ""
log_info "✅ Configuration complete:"
echo "  • Reality keys saved to /etc/xray/.keys"
echo "  • Shadowsocks password saved to /etc/xray/.keys"
echo "  • VLESS port: 4443"
echo "  • Shadowsocks port: $SS_port"
echo ""

# ============================================
# STEP 6: Install Hysteria2
# ============================================
log_info "🚀 Step 6/9: Installing Hysteria2..."
mkdir -p /etc/hysteria

# Get latest version (fixed jq filter)
HY_VERSION=$(curl -s https://api.github.com/repos/apernet/hysteria/releases/latest | jq -r '.tag_name' | sed 's/app\/v//')

# Fallback if version is empty
if [ -z "$HY_VERSION" ] || [ "$HY_VERSION" = "null" ]; then
    log_warning "Could not fetch latest Hysteria version, using fallback..."
    HY_VERSION="2.4.1"  # Known stable version
fi

log_info "Latest Hysteria version: ${HY_VERSION}"

# Download and install
wget -q https://github.com/apernet/hysteria/releases/download/app/v${HY_VERSION}/hysteria-linux-amd64 -O /usr/local/bin/hysteria
chmod +x /usr/local/bin/hysteria

# Generate auth secrets
HY_AUTH=$(openssl rand -hex 32)
HY_OBFS=$(openssl rand -hex 16)

# Create config (TLS paths will be set after certbot)
cat > /etc/hysteria/config.yaml << EOF
listen: :443
tls:
    cert: /etc/letsencrypt/live/${SUB_DOMAIN}/fullchain.pem
    key: /etc/letsencrypt/live/${SUB_DOMAIN}/privkey.pem
auth:
    type: password
    password: ${HY_AUTH}
obfs:
    type: salamander
    salamander:
        password: ${HY_OBFS}
log:
    level: info
    output: /var/log/lumon/hysteria.log
EOF

# Save auth to config for later reference
jq --arg auth "$HY_AUTH" --arg obfs "$HY_OBFS" '.hysteria_auth = $auth | .hysteria_obfs = $obfs' /etc/lumon/lumon_config.json > /tmp/lc.json && mv /tmp/lc.json /etc/lumon/lumon_config.json

# Create systemd service
cat > /etc/systemd/system/hysteria.service << EOF
[Unit]
Description=Hysteria2 Service
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/hysteria server -c /etc/hysteria/config.yaml
Restart=on-failure
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable hysteria
# Don't start yet - need SSL certs first

log_success "Hysteria2 v${HY_VERSION} installed"

# ============================================
# STEP 7: Nginx Configuration
# ============================================
log_info "🌍 Step 7/9: Configuring Nginx..."

# Create decoy directory
mkdir -p /var/www/decoy

# Nginx config for subscription domain
cat > /etc/nginx/sites-available/lumon << EOF
server {
    listen 80;
    server_name ${SUB_DOMAIN};
    return 301 https://\$server_name\$request_uri;
}

server {
    listen 443 ssl http2;
    server_name ${SUB_DOMAIN};

    ssl_certificate /etc/letsencrypt/live/${SUB_DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${SUB_DOMAIN}/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers on;

    # Security headers
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Rate limiting (optional)
    # limit_req_zone \$binary_remote_addr zone=sub_limit:10m rate=10r/s;
    # limit_req zone=sub_limit burst=20 nodelay;

    # Subscription endpoint only
    location /sub/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300;
    }

    # Block everything else
    location / {
        return 404;
    }

    # Health check
    location /health {
        access_log off;
        return 200 "OK\n";
        add_header Content-Type text/plain;
    }
}
EOF

# Nginx config for decoy domain
cat > /etc/nginx/sites-available/decoy << EOF
server {
    listen 80;
    server_name ${DECOY_DOMAIN};
    return 301 https://\$server_name\$request_uri;
}

server {
    listen 443 ssl http2;
    server_name ${DECOY_DOMAIN};

    ssl_certificate /etc/letsencrypt/live/${DECOY_DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DECOY_DOMAIN}/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers on;

    root /var/www/decoy;
    index index.html;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    location / {
        try_files \$uri \$uri/ =404;
    }

    # Block sensitive files
    location ~ /\. {
        deny all;
    }
}
EOF

# Enable sites
ln -sf /etc/nginx/sites-available/lumon /etc/nginx/sites-enabled/
ln -sf /etc/nginx/sites-available/decoy /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test config
# nginx -t

# Don't test/reload yet - certificates don't exist yet
# Will test and reload after certbot in Step 8
log_info "Nginx config created (waiting for SSL certs)"

# ============================================
# STEP 8: SSL Certificates (Let's Encrypt)
# ============================================
log_info "🔒 Step 8/9: Obtaining SSL certificates..."

# Verify domains resolve to this server
log_info "Verifying domain DNS records..."
for domain in "${SUB_DOMAIN}" "${DECOY_DOMAIN}"; do
    if ! host "$domain" | grep -q "$(curl -s https://ifconfig.me)"; then
        log_warning "⚠️  $domain may not point to this server (${SERVER_IP})"
        log_warning "   Make sure A record is set correctly before proceeding"
    fi
done

# Stop nginx for standalone certbot mode
log_info "Stopping nginx for certificate issuance..."
systemctl stop nginx

# Ensure port 80 is free
if ss -tlnp | grep -q ':80 '; then
    log_error "Port 80 is still in use. Cannot obtain certificates."
    exit 1
fi

# Get certificates with error handling
CERTBOT_ARGS="--non-interactive --agree-tos --email ${LETSENCRYPT_EMAIL:-admin@${SUB_DOMAIN}}"

log_info "Requesting certificate for ${SUB_DOMAIN}..."
if ! certbot certonly --standalone -d "${SUB_DOMAIN}" ${CERTBOT_ARGS}; then
    log_error "Failed to obtain certificate for ${SUB_DOMAIN}"
    log_error "Check that:"
    log_error "  - Domain A record points to this server"
    log_error "  - Port 80 is not blocked by firewall"
    log_error "  - No other service is using port 80"
    exit 1
fi

log_info "Requesting certificate for ${DECOY_DOMAIN}..."
if ! certbot certonly --standalone -d "${DECOY_DOMAIN}" ${CERTBOT_ARGS}; then
    log_error "Failed to obtain certificate for ${DECOY_DOMAIN}"
    exit 1
fi

# Setup auto-renewal
if ! crontab -l 2>/dev/null | grep -q "certbot renew"; then
    (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet --post-hook 'systemctl reload nginx'") | crontab -
    log_success "Auto-renewal configured"
fi

# NOW test and reload nginx (certificates exist!)
log_info "Testing and reloading Nginx..."
nginx -t

# Start nginx if stopped, otherwise reload
if systemctl is-active --quiet nginx; then
    systemctl reload nginx
else
    systemctl start nginx
fi

# Now we can start Hysteria (needs SSL certs)
systemctl start hysteria

log_success "SSL certificates obtained and Nginx reloaded"

# ============================================
# STEP 9: Python Application Setup
# ============================================
log_info "🐍 Step 9/9: Setting up Python application..."

# Create app directory
mkdir -p /opt/lumon
cd /opt/lumon

# Clone or copy the project
# For now, we'll create a minimal setup
python3 -m venv venv
source venv/bin/activate

pip install --upgrade pip
pip install fastapi uvicorn sqlalchemy psycopg2-binary typer questionary cryptography python-multipart jinja2 requests

# Create CLI entry point
cat > /usr/local/bin/lumon-cli << 'EOFCLI'
#!/bin/bash
cd /opt/lumon
source venv/bin/activate
exec python3 -m lumon.cli_menu "$@"
EOFCLI
chmod +x /usr/local/bin/lumon-cli

# Create systemd service for LUMON API
cat > /etc/systemd/system/lumon-api.service << EOF
[Unit]
Description=LUMON Panel API
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/lumon
ExecStart=/opt/lumon/venv/bin/uvicorn lumon.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
Environment=PATH=/opt/lumon/venv/bin

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable lumon-api
systemctl start lumon-api

log_success "Python application installed"

# ============================================
# Create Decoy Website
# ============================================
log_info "🎭 Creating decoy website..."

cat > /var/www/decoy/index.html << 'EOFHTML'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LUMON Industries - Employee Portal</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#1a1a2e;color:#eee;min-height:100vh;display:flex;align-items:center;justify-content:center}
        .container{background:#16213e;padding:40px;border-radius:10px;box-shadow:0 10px 40px rgba(0,0,0,.5);max-width:400px;width:100%}
        .logo{text-align:center;margin-bottom:30px}
        .logo h1{color:#0f3460;font-size:2em;letter-spacing:5px}
        .form-group{margin-bottom:20px}
        .form-group label{display:block;margin-bottom:8px;color:#aaa;font-size:.9em}
        .form-group input{width:100%;padding:12px;border:1px solid #0f3460;border-radius:5px;background:#1a1a2e;color:#fff;font-size:1em}
        .form-group input:focus{outline:none;border-color:#e94560}
        button{width:100%;padding:12px;background:#e94560;border:none;border-radius:5px;color:#fff;font-size:1em;cursor:pointer;transition:background .3s}
        button:hover{background:#c73e54}
        .footer{text-align:center;margin-top:20px;color:#666;font-size:.8em}
    </style>
</head>
<body>
    <div class="container">
        <div class="logo"><h1>LUMON</h1><p>Employee Portal</p></div>
        <form onsubmit="event.preventDefault();">
            <div class="form-group"><label>Employee ID</label><input type="text" placeholder="Enter your ID"></div>
            <div class="form-group"><label>Password</label><input type="password" placeholder="Enter password"></div>
            <button type="submit">Sign In</button>
        </form>
        <div class="footer">
            <p>© 2024 LUMON Industries. All rights reserved.</p>
            <p>This is a secure corporate portal.</p>
        </div>
    </div>
</body>
</html>
EOFHTML

log_success "Decoy website created at /var/www/decoy"
log_warning "💡 Tip: You can replace /var/www/decoy/index.html with your own decoy"

# ============================================
# Setup Backups
# ============================================
log_info "💾 Setting up automatic backups..."

mkdir -p /var/backups/lumon

# Backup script for database
cat > /usr/local/bin/lumon-backup-db << 'EOFBK'
#!/bin/bash
CONFIG="/etc/lumon/lumon_config.json"
DB_PASSWORD=$(jq -r '.db_password' "$CONFIG")
BACKUP_PATH=$(jq -r '.backup_path' "$CONFIG")
RETENTION=$(jq -r '.backup_retention_days' "$CONFIG")

mkdir -p "$BACKUP_PATH"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_PATH/db-${TIMESTAMP}.sql.gz"

pg_dump -U lumon -h localhost lumon_db | gzip > "$BACKUP_FILE"

# Remove old backups
find "$BACKUP_PATH" -name "db-*.sql.gz" -mtime +$RETENTION -delete

echo "Backup created: $BACKUP_FILE"
EOFBK
chmod +x /usr/local/bin/lumon-backup-db

# Add to cron (daily at 3 AM)
if ! crontab -l | grep -q "lumon-backup-db"; then
    (crontab -l 2>/dev/null; echo "0 3 * * * /usr/local/bin/lumon-backup-db >> /var/log/lumon/backup.log 2>&1") | crontab -
fi

log_success "Automatic backups configured (daily at 3:00)"

# ============================================
# Installation Complete
# ============================================
echo ""
echo "================================================"
echo -e "  ${GREEN}✅ LUMON Panel Installation Complete!${NC}"
echo "================================================"
echo ""
echo -e "  📡 Subscription: https://${SUB_DOMAIN}"
echo -e "  🎭 Decoy:        https://${DECOY_DOMAIN}"
echo -e "  🗄️  Database:    lumon_db (PostgreSQL 16)"
echo -e "  📁 Config:       /etc/lumon/lumon_config.json"
echo -e "  📝 Logs:         /var/log/lumon/"
echo -e "  💾 Backups:      /var/backups/lumon/"
echo ""
echo -e "  🔐 Save this database password:"
echo -e "     ${YELLOW}${DB_PASSWORD}${NC}"
echo ""
echo -e "  🚀 To access CLI menu:"
echo -e "     ${YELLOW}lumon-cli${NC}" 
echo ""
echo "  📋 Next steps:"
echo "     1. Copy lumon/ files to /opt/lumon/"
echo "     2. Run database migrations"
echo "     3. Create your first user"
echo ""
echo "================================================"
