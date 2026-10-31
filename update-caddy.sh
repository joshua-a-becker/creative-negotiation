#!/bin/bash

# Caddy HTTPS Setup Script
# Run this ON the server (157.245.212.151)


echo "Updating Caddy reverse proxy..."

# Create Caddyfile
cat > /etc/caddy/Caddyfile << 'EOF'
platformdev.negotiation.education {
    reverse_proxy localhost:3000
}
negotiation.socialscience.app {
    reverse_proxy localhost:3000
}
EOF

cat /etc/caddy/Caddyfile

# Reload Caddy
systemctl reload caddy
systemctl enable caddy

echo "Caddy update completed!"