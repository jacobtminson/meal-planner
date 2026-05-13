#!/usr/bin/env bash
# Run once on the Debian server to set up the project.
# Works regardless of where the repo was cloned.
set -e

# Resolve project root from this script's location (deploy/ is one level down)
PROJECT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
echo "==> Project root: $PROJECT"

echo "==> Creating virtualenv"
python3 -m venv "$PROJECT/venv"
"$PROJECT/venv/bin/pip" install --upgrade pip
"$PROJECT/venv/bin/pip" install -r "$PROJECT/requirements.txt"

echo "==> Initialising database"
"$PROJECT/venv/bin/python" "$PROJECT/db/init_db.py"

echo "==> Creating log directory"
mkdir -p "$PROJECT/logs"

echo "==> Creating .env from example if not present"
if [ ! -f "$PROJECT/.env" ]; then
    cp "$PROJECT/.env.example" "$PROJECT/.env"
    echo "    Created $PROJECT/.env — fill in your credentials before restarting the service."
fi

echo "==> Installing systemd service"
# Substitute the real project path into the service file
sed "s|/opt/meals|$PROJECT|g" "$PROJECT/deploy/meals-api.service" \
    > /etc/systemd/system/meals-api.service
systemctl daemon-reload
systemctl enable meals-api
systemctl start meals-api
systemctl status meals-api --no-pager || true

if [ ! -f /etc/nginx/sites-available/meals.conf ]; then
    echo "==> Installing Nginx config (first time)"
    sed "s|/opt/meals|$PROJECT|g" "$PROJECT/deploy/nginx-meals.conf" \
        > /etc/nginx/sites-available/meals.conf
    ln -sf /etc/nginx/sites-available/meals.conf /etc/nginx/sites-enabled/meals.conf
    nginx -t && systemctl reload nginx
else
    echo "==> Nginx config already exists — skipping (edit /etc/nginx/sites-available/meals.conf manually)"
fi

echo ""
echo "Done! Next steps:"
echo "  1. Copy .env.example to .env and fill in your credentials"
echo "  2. Run: docker compose -f $PROJECT/docker-compose.yml up -d"
echo "  3. Get your Mealie API token from the Mealie UI and add it to .env"
echo "  4. Restart the API: systemctl restart meals-api"
echo "  5. Add cron jobs: crontab -e"
echo "     0 8  * * 1  $PROJECT/venv/bin/python $PROJECT/scripts/weekly_curation.py >> $PROJECT/logs/curation.log 2>&1"
echo "     0 20 * * 3  $PROJECT/venv/bin/python $PROJECT/scripts/deadline_check.py  >> $PROJECT/logs/deadline.log  2>&1"
echo "  6. Get SSL certs: certbot --nginx -d meals.yourdomain.com -d recipes.yourdomain.com"
