#!/bin/bash
# Bootstrap a fresh Ubuntu 24.04 VPS after verifying SSH key access.
set -euo pipefail
test "$(id -u)" = 0
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl ufw unattended-upgrades
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

# Reserve disk-backed memory for bursts on the 2 GB VPS.
if ! swapon --noheadings --show | grep -q .; then
    if ! test -e /swapfile-airate; then
        fallocate -l 2G /swapfile-airate
        chmod 600 /swapfile-airate
        mkswap /swapfile-airate
    fi
    swapon /swapfile-airate
    grep -q '^/swapfile-airate ' /etc/fstab || printf '\n/swapfile-airate none swap sw 0 0\n' >> /etc/fstab
fi
printf 'vm.swappiness=10\n' > /etc/sysctl.d/90-airate.conf
sysctl -p /etc/sysctl.d/90-airate.conf

# This script requires that key authentication has already succeeded.
test -s /root/.ssh/authorized_keys
cat > /etc/ssh/sshd_config.d/00-airate.conf <<'EOF'
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
EOF
sshd -t
systemctl reload ssh
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw default deny incoming
ufw default allow outgoing
ufw --force enable
install -d -m 0700 /opt/airate
docker --version
docker compose version
ufw status
free -m
