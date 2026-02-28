# 🌟 LUMON Panel

> Minimalistic CLI panel for Hysteria2 & Xray Core management

![LUMON](https://img.shields.io/badge/version-1.0.0-blue.svg)
![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04-orange.svg)
![Python](https://img.shields.io/badge/Python-3.12-yellow.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

---

## ✨ Features

- 🚀 One-click installation on Ubuntu 24.04
- 👥 User management with auto-generated credentials
- 🔗 Subscription links: `vless://` + `hysteria2://`
- 🎭 Decoy website support (fake login page)
- 🔒 Automatic Let's Encrypt SSL certificates
- 🖥️ Interactive CLI menu (no heavy web UI)
- 📊 Traffic monitoring & server stats
- 💾 Automatic PostgreSQL backups
- 📱 Base64 subscription for Hiddify, v2rayNG, Streisand

---

## 📋 Requirements

| Component | Version | Notes |
|-----------|---------|-------|
| OS | Ubuntu 24.04 | Clean installation recommended |
| RAM | 1 GB minimum | 2 GB recommended |
| Disk | 10 GB | For logs and backups |
| Domains | 2 | One for subscription, one for decoy |
| Ports | 80, 443 (TCP), 443 (UDP) | Open in firewall |

---

## 🚀 Quick Installation

### Step 1: Clone repository

```bash
git clone https://github.com/MAX-TAC/lumon-panel.git
cd lumon-panel
