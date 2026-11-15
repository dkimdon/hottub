from bwa.client import Client
from bwa.discovery import find_spa

# Discover the spa's IP automatically
ip = find_spa()
print(f"Found spa at {ip}")

# Connect and read current status
with Client(ip) as spa:
    status = spa.poll_until_status()
    print(status)
    # <Status 10:30AM 102.0/104.0°F ready heating high>
