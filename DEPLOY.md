# 🚀 Two-Server Deployment - Simple Guide

## Setup
- **Backend Server (95.142.102.148)**: Flask API + PostgreSQL + Redis
- **Frontend Server (95.142.102.147)**: Next.js Frontend + Next.js Admin

---

## Step 1: Generate Secrets (On Your Windows Machine)

```powershell
cd "d:\advanced print match system"
.\generate-secrets.ps1
```
DB_PASSWORD=PnvbpMCUwAODNrMbvCCOpw0rS9AcS1zu3mOA6DFWE
SECRET_KEY=WhV2Zwq1VGkI3ugXuyovHhWIvjyiRXSDLs42AbxmJxTPwvCSSTHdNE7QXWOm7IP8dPCzqYQV3cSVHVyZCL1Q
JWT_SECRET_KEY=cdOAtS1VPF0CJwh47qLBzc7akVDbX8gNdyy1UTADA0X5LzTqHtSqNDqUGF7mnwv6xITewTh6ZpowxkeYcY7w

Save the `.env.production` file that is generated!

---

## Step 2: Deploy Backend Server (95.142.102.148)

### SSH to Backend Server

```powershell
ssh keyadmin@95.142.102.148
```

### Clone Repository and Configure

```bash
# Navigate to deployment directory
cd /opt
sudo mkdir -p sarapps
sudo chown keyadmin:keyadmin sarapps
cd sarapps

# Clone repository (MUCH FASTER!)
git clone https://github.com/JawadKhan65/SARAPPS.git .

# Or if already cloned, just pull latest:
# git pull

# Upload your .env.production file
# Exit SSH and from your Windows machine run:
```

```powershell
scp "d:\advanced print match system\.env.production" keyadmin@95.142.102.148:/opt/sarapps/
```

### Back on Backend Server

```bash
# SSH back in
ssh keyadmin@95.142.102.148

cd /opt/sarapps
chmod +x deploy-backend.sh
./deploy-backend.sh
```

---

## Step 3: Deploy Frontend Server (95.142.102.147)

### SSH to Frontend Server

```powershell
ssh keyadmin@95.142.102.147
```

### Clone Repository and Configure

```bash
# Navigate to deployment directory
cd /opt
sudo mkdir -p sarapps
sudo chown keyadmin:keyadmin sarapps
cd sarapps

# Clone repository (MUCH FASTER!)
git clone https://github.com/JawadKhan65/SARAPPS.git .

# Or if already cloned, just pull latest:
# git pull

# Upload your .env.production file
# Exit SSH and from your Windows machine run:
```

```powershell
scp "d:\advanced print match system\.env.production" keyadmin@95.142.102.147:/opt/sarapps/
```

### Back on Frontend Server

```bash
# SSH back in
ssh keyadmin@95.142.102.147

cd /opt/sarapps
chmod +x deploy-frontend.sh
./deploy-frontend.sh
```

---

## Done!

Visit: https://sarapps.com

---

## Quick Update (After First Deployment)

For future updates:

```bash
# On either server
cd /opt/sarapps
git pull
docker-compose down
docker-compose up -d --build
```

