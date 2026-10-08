#!/bin/bash
# Install delivery controls from a reviewed, root-owned /opt/airate/deploy.
set -euo pipefail
test "$(id -u)" = 0
public_key=${1:?Usage: setup-delivery.sh path/to/deploy-key.pub}
test -f "$public_key"
ssh-keygen -l -f "$public_key" >/dev/null
test "$(wc -l < "$public_key")" -le 1
cd /opt/airate/deploy
bash -n release.sh ssh-gate.sh
install -o root -g root -m 0755 release.sh /usr/local/sbin/airate-release
install -o root -g root -m 0755 ssh-gate.sh /usr/local/sbin/airate-ssh-gate
id airate-deploy >/dev/null 2>&1 || useradd --create-home --shell /bin/bash airate-deploy
chown root:root /home/airate-deploy
chmod 755 /home/airate-deploy
install -d -o root -g root -m 0755 /home/airate-deploy/.ssh
{ printf 'restrict,command="/usr/local/sbin/airate-ssh-gate" '; tr -d '\r' < "$public_key"; } > /home/airate-deploy/.ssh/authorized_keys
chown root:root /home/airate-deploy/.ssh/authorized_keys
chmod 644 /home/airate-deploy/.ssh/authorized_keys
install -d -o root -g root -m 0755 /var/lib/airate-ci
install -d -o airate-deploy -g airate-deploy -m 0700 /var/lib/airate-ci/incoming
printf 'airate-deploy ALL=(root) NOPASSWD: /usr/local/sbin/airate-release\n' > /etc/sudoers.d/airate-deploy
chmod 440 /etc/sudoers.d/airate-deploy
visudo -cf /etc/sudoers.d/airate-deploy
install -m 0644 airate-backup.service airate-backup.timer /etc/systemd/system/
systemctl daemon-reload
# Start the timer only after the database is available on the target VPS.
echo 'Delivery installed. After restoring the database: systemctl enable --now airate-backup.timer'
