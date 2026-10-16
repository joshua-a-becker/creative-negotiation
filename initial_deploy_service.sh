#!/bin/bash

# Empirica Deployment Script
# Hard-coded for this project

source ./server_settings.sh

echo "Deploying to $IP_ADDRESS..."

# Bundle the application
empirica bundle

# Transfer bundle to server
scp -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no "$BUNDLE_FILENAME" "$REMOTE_USER@$IP_ADDRESS:~/"

# Transfer Scoring to server (before the service starts, so the scorer is found at startup)
scp -r -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no ./score_offer "$REMOTE_USER@$IP_ADDRESS:~/"

# Install Empirica and kill any existing empirica processes
ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no "$REMOTE_USER@$IP_ADDRESS" << EOF
pkill -f empirica || true
curl https://install.empirica.dev | sh -s
EOF

# Set up service
ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no "$REMOTE_USER@$IP_ADDRESS" 'sudo bash -s' < ./setup_service.sh


# set caddyfile
ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no "$REMOTE_USER@$IP_ADDRESS" 'sudo bash -s' < ./setup-caddy.sh

# set pagefile
ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no "$REMOTE_USER@$IP_ADDRESS" 'sudo bash -s' < ./create_pagefile.sh


# download logs
# scp -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no "$REMOTE_USER@$IP_ADDRESS:~/empirica.log" .



# check caddyfile
# ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no "$REMOTE_USER@$IP_ADDRESS" cat /etc/caddy/Caddyfile


# update caddyfile
# ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no "$REMOTE_USER@$IP_ADDRESS" 'sudo bash -s' < ./update-caddy.sh

# monitor
# ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no "$REMOTE_USER@$IP_ADDRESS" "sudo journalctl -u empirica -f"

# ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no "$REMOTE_USER@$IP_ADDRESS" "sudo journalctl -u empirica -n 100 --no-pager " > log.txt


# ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no "$REMOTE_USER@$IP_ADDRESS" "sudo journalctl -u empirica --no-pager; sudo journalctl -u empirica -f" > empirica.log

# copy 