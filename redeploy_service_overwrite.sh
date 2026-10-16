#!/bin/bash

# Empirica Deployment Script
# Hard-coded for this project

# copy treatments

source ./server_settings.sh

# scp -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no "$REMOTE_USER@$IP_ADDRESS:/root/.empirica/treatments.yaml" .empirica/treatments.yaml

set -e  # Exit on any error

echo "Deploying to $IP_ADDRESS..."

# Bundle the application
empirica bundle

# Transfer bundle to server
scp -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no "$BUNDLE_FILENAME" "$REMOTE_USER@$IP_ADDRESS:~/"

# Transfer Scoring to server
scp -r -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no ./../score_offer "$REMOTE_USER@$IP_ADDRESS:~/"

# restart service
ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no "$REMOTE_USER@$IP_ADDRESS" "sudo systemctl restart empirica && sudo systemctl status empirica"