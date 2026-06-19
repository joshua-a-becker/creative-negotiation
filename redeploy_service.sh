#!/bin/bash

# Empirica Deployment Script
# Hard-coded for this project

# copy treatments



IP_ADDRESS="167.99.161.107"
SSH_KEY_PATH="$HOME/.ssh/id_rsa"
BUNDLE_FILENAME="VideoChatApp.tar.zst"
REMOTE_USER="root" 

# don't overwrite the remote treament [does overwrite local!]
scp -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no "$REMOTE_USER@$IP_ADDRESS:/root/.empirica/treatments.yaml" .empirica/treatments.yaml

set -e  # Exit on any error

echo "Deploying to $IP_ADDRESS..."

# Bundle the application
empirica bundle

# Transfer bundle to server
scp -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no "$BUNDLE_FILENAME" "$REMOTE_USER@$IP_ADDRESS:~/"

# restart service
ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no "$REMOTE_USER@$IP_ADDRESS" "sudo systemctl restart empirica && sudo systemctl status empirica"