#!/bin/bash

# Update system
sudo apt-get update
sudo apt-get upgrade -y

# Install system dependencies
sudo apt-get install -y python3 python3-pip python3-venv nginx
sudo apt-get install -y poppler-utils  # For pdf2image
sudo apt-get install -y tesseract-ocr  # For OCR
sudo apt-get install -y libtesseract-dev  # Tesseract development files

# Create application directory
sudo mkdir -p /var/www/pdfapp
sudo chown -R $USER:$USER /var/www/pdfapp

# Create virtual environment
cd /var/www/pdfapp
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Create necessary directories
mkdir -p uploads converted static templates

# Copy templates (you might want to handle this in deployment)
# cp -r /path/to/your/templates/* templates/

# Setup Nginx
sudo tee /etc/nginx/sites-available/pdfapp << EOF
server {
    listen 80;
    server_name _;

    # Maximum upload size
    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /static {
        alias /var/www/pdfapp/static;
    }
}
EOF

# Enable site
sudo ln -sf /etc/nginx/sites-available/pdfapp /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test nginx configuration
sudo nginx -t

# Install and configure systemd service
sudo tee /etc/systemd/system/pdfapp.service << EOF
[Unit]
Description=Gunicorn instance to serve PDF App
After=network.target

[Service]
User=$USER
Group=www-data
WorkingDirectory=/var/www/pdfapp
Environment="PATH=/var/www/pdfapp/venv/bin"
Environment="TESSERACT_PATH=/usr/bin/tesseract"
ExecStart=/var/www/pdfapp/venv/bin/gunicorn --workers 3 --bind 0.0.0.0:8000 wsgi:app

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and start services
sudo systemctl daemon-reload
sudo systemctl start pdfapp
sudo systemctl enable pdfapp
sudo systemctl restart nginx

# Configure firewall
sudo ufw allow 'Nginx Full'
sudo ufw allow ssh
sudo ufw --force enable

echo "Setup completed successfully!"
echo "Application will be available at: http://$(curl -s ifconfig.me)"