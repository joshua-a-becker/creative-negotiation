source ./server_settings.sh

ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no "$REMOTE_USER@$IP_ADDRESS" "mv .empirica/local/tajriba.json .empirica/local/tajriba.json.bak.\$(date +%Y%m%d%H%M%S) && sudo systemctl restart empirica"