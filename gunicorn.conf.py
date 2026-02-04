# Gunicorn configuration file

# Timeout for workers (in seconds)
# Increased to handle slow web scraping + Claude API calls for all clues
timeout = 300

# Number of worker processes
workers = 2

# Binding
bind = "0.0.0.0:8080"

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
