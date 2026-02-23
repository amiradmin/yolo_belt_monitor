# nginx/Dockerfile
FROM nginx:1.25-alpine

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/

# Create directories for SSL certificates
RUN mkdir -p /etc/nginx/ssl /var/log/nginx

# Copy SSL certificates (if any)
# COPY ssl/ /etc/nginx/ssl/