# Deploying Spotify MCP Server on Hostinger VPS

## Prerequisites

- Hostinger VPS plan (KVM 1 or higher recommended)
- Domain name (optional but recommended)
- Your Spotify MCP server repository

## Step 1: Set Up Hostinger VPS

### 1.1 Access Your VPS
```bash
# SSH into your VPS (replace with your VPS IP)
ssh root@your-vps-ip
```

### 1.2 Update System
```bash
sudo apt update && sudo apt upgrade -y
```

### 1.3 Install Required Packages
```bash
# Install Python, Git, and essential tools
sudo apt install -y python3 python3-pip python3-venv git nginx certbot python3-certbot-nginx ufw

# Install Node.js for uvx (if needed)
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install uv and uvx
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

## Step 2: Deploy Your Application

### 2.1 Clone Your Repository
```bash
# Navigate to web directory
cd /var/www

# Clone your Spotify MCP server
sudo git clone https://github.com/oe-ai-experiments/spotify-mcp-server.git
sudo chown -R $USER:$USER spotify-mcp-server
cd spotify-mcp-server
```

### 2.2 Set Up Environment
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Or use uvx for production
uvx --from . spotify-mcp-server --help
```

### 2.3 Configure Environment Variables
```bash
# Create environment file
sudo nano /etc/environment

# Add your Spotify credentials
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
SPOTIFY_REDIRECT_URI=https://yourdomain.com/callback
```

### 2.4 Create Configuration File
```bash
# Create config.json with your VPS domain
cat > config.json << EOF
{
  "spotify": {
    "client_id": "\${SPOTIFY_CLIENT_ID}",
    "client_secret": "\${SPOTIFY_CLIENT_SECRET}",
    "redirect_uri": "\${SPOTIFY_REDIRECT_URI}"
  },
  "server": {
    "host": "0.0.0.0",
    "port": 8000
  },
  "api": {
    "base_url": "https://api.spotify.com/v1",
    "timeout": 30,
    "retry_attempts": 3
  }
}
EOF
```

## Step 3: Set Up Production Server

### 3.1 Create Systemd Service
```bash
# Create service file
sudo nano /etc/systemd/system/spotify-mcp.service
```

Add this content:
```ini
[Unit]
Description=Spotify MCP Server
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/spotify-mcp-server
Environment=PATH=/var/www/spotify-mcp-server/venv/bin
EnvironmentFile=/etc/environment
ExecStart=/var/www/spotify-mcp-server/venv/bin/python -m spotify_mcp_server.main --config /var/www/spotify-mcp-server/config.json
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### 3.2 Start the Service
```bash
# Reload systemd and start service
sudo systemctl daemon-reload
sudo systemctl enable spotify-mcp
sudo systemctl start spotify-mcp

# Check status
sudo systemctl status spotify-mcp
```

## Step 4: Configure Nginx Reverse Proxy

### 4.1 Create Nginx Configuration
```bash
sudo nano /etc/nginx/sites-available/spotify-mcp
```

Add this configuration:
```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 86400;
    }

    # Handle MCP WebSocket connections
    location /mcp {
        proxy_pass http://127.0.0.1:8000/mcp;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 4.2 Enable the Site
```bash
# Enable the site
sudo ln -s /etc/nginx/sites-available/spotify-mcp /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx
```

## Step 5: Set Up SSL Certificate

### 5.1 Configure Firewall
```bash
# Allow necessary ports
sudo ufw allow 'Nginx Full'
sudo ufw allow ssh
sudo ufw enable
```

### 5.2 Get SSL Certificate
```bash
# Get Let's Encrypt certificate
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Test auto-renewal
sudo certbot renew --dry-run
```

## Step 6: Initial Authentication Setup

### 6.1 Run Authentication Setup
```bash
# SSH into your VPS and run setup
cd /var/www/spotify-mcp-server
source venv/bin/activate
python -m spotify_mcp_server.main --setup-auth --config config.json
```

### 6.2 Configure MCP Client
Update your MCP client configuration to use your Hostinger server:

```json
{
  "mcpServers": {
    "spotify": {
      "command": "curl",
      "args": [
        "-X", "POST",
        "-H", "Content-Type: application/json",
        "-d", "@-",
        "https://yourdomain.com/mcp"
      ]
    }
  }
}
```

## Step 7: Monitoring and Maintenance

### 7.1 Check Logs
```bash
# Service logs
sudo journalctl -u spotify-mcp -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### 7.2 Update Deployment
```bash
# Update code
cd /var/www/spotify-mcp-server
sudo git pull origin main

# Restart service
sudo systemctl restart spotify-mcp
```

## Estimated Costs

- **Hostinger VPS KVM 1**: ~$3.99/month
- **Domain**: ~$8.99/year (if needed)
- **Total**: ~$4-5/month

## Troubleshooting

### Common Issues:

1. **Service won't start**: Check logs with `sudo journalctl -u spotify-mcp`
2. **Nginx 502 error**: Ensure the service is running on port 8000
3. **SSL issues**: Run `sudo certbot renew` and restart nginx
4. **Token persistence**: Ensure `/var/www/spotify-mcp-server` has proper permissions

### Health Check Endpoint:
```bash
# Test if server is running
curl https://yourdomain.com/health
```

## Security Best Practices

1. **Keep system updated**: `sudo apt update && sudo apt upgrade`
2. **Use strong passwords** for VPS access
3. **Enable fail2ban**: `sudo apt install fail2ban`
4. **Regular backups** of your configuration and tokens
5. **Monitor logs** for unusual activity

## Conclusion

Your Spotify MCP server is now deployed on Hostinger VPS with:
- ✅ Production-ready setup with systemd
- ✅ Nginx reverse proxy with SSL
- ✅ Automatic service restart on failure
- ✅ Secure environment variable management
- ✅ WebSocket support for MCP protocol
