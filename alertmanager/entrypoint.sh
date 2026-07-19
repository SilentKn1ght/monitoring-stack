#!/bin/sh
set -e
sed "s/__TELEGRAM_BOT_TOKEN__/${TELEGRAM_BOT_TOKEN}/g; s/__TELEGRAM_CHAT_ID__/${TELEGRAM_CHAT_ID}/g" /etc/alertmanager/alertmanager.tmpl > /alertmanager/alertmanager.yml
exec /bin/alertmanager --config.file=/alertmanager/alertmanager.yml --storage.path=/alertmanager --web.external-url=https://84.46.248.57/alertmanager/ --web.route-prefix=/ --cluster.listen-address= --log.level=info "$@"
