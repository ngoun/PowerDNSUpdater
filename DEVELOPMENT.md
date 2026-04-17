# Development Guide — PowerDNS Dynamic IP Updater

Information for developers who want to modify, extend, or debug the app.

## Project Structure

```
powerdns-updater/
├── dynamicdns.py          # Main application (single file)
├── requirements.txt       # Python dependencies
├── build.bat              # Build script (creates .exe)
├── README.md              # Full user documentation
├── QUICKSTART.md          # 5-minute setup guide
└── DEVELOPMENT.md         # This file
```

## Architecture

Single-file Python app using:

- **pystray** — system tray integration
- **tkinter** — GUI for settings dialog
- **requests** — HTTP for PowerDNS API calls
- **Pillow** — tray icon rendering

### Main Class: `PowerDNSUpdater`

```python
class PowerDNSUpdater:
    # Settings I/O
    _load_settings()                    # Load from JSON file
    _save_settings()                    # Save to JSON file
    _delete_settings()                  # Delete config file and reset to defaults

    # Network operations
    _get_public_ipv4()                  # Fetch IPv4 from services
    _get_public_ipv6()                  # Fetch IPv6 from services
    _do_pdns_update(type, ip)           # PATCH to PowerDNS API (single record)
    _do_pdns_update_multi(updates_dict) # PATCH to PowerDNS API (multiple records)

    # IP validation
    _is_valid_ipv4()         # Validate IPv4 format
    _is_valid_ipv6()         # Validate IPv6 format

    # Background loop
    _update_loop()           # Main check/update thread
    _restart_loop()          # Stop/start the loop

    # UI
    _show_settings()         # Settings dialog window with form and buttons
    _action_update_now()     # Force immediate IP check and DNS update
    _action_open_settings()  # Open settings dialog
    _make_icon()             # Generate tray icon image
    _make_menu()             # Create tray menu

    # System integration
    _set_autostart()         # Write to Windows registry
    _set_status(msg)         # Update tooltip + status

    run()                    # Entry point
```

## Settings Format

File: `%APPDATA%\PowerDNSUpdater\settings.json`

```json
{
  "pdns_url": "http://192.168.1.10:8081",
  "api_key": "secret-key",
  "zone": "example.com",
  "hostname": "home",
  "record_type": "A",
  "ttl": 3600,
  "interval": 300,
  "enabled": true,
  "autostart": false,
  "last_ipv4": "203.0.113.45",
  "last_ipv6": "",
  "last_update": "2026-04-16 14:32:15",
  "last_status": "Updated A -> 203.0.113.45"
}
```

## Code Flow

### Startup
1. Load settings from JSON
2. Create system tray icon (red "P")
3. Start background update loop
4. Show tray menu

### Main Loop (every N seconds)
```
Check if enabled?
  → Detect public IP (IPv4 or IPv6 based on record_type)
    → Validate IP format
    → Compare to last recorded IP
      → If different: call _do_pdns_update()
      → If same: log "unchanged"
    → Update status in tooltip
  → Wait interval seconds
  → Repeat
```

### Update Request (Single Record)
```
_do_pdns_update(record_type, ip):
  → Build zone FQDN (ensure trailing dot)
  → Build FQDN of hostname (e.g., home.example.com)
  → Create PATCH payload (RRset replacement)
  → Send to PowerDNS API
  → Parse response code (204 = success)
  → Update last_ipv4/last_ipv6 and timestamp
  → Set status message
  → Save to JSON
```

### Update Request (Multiple Records)
```
_do_pdns_update_multi(updates={'A': ipv4, 'AAAA': ipv6}):
  → Build zone FQDN (ensure trailing dot)
  → Build FQDN of hostname
  → Create PATCH payload with multiple RRsets
  → Send single request to PowerDNS API (atomic)
  → Parse response code (204 = success)
  → Update last_ipv4/last_ipv6 and timestamp
  → Set status message
  → Save to JSON
```

**Advantage**: Updates both A and AAAA records in a single API call (atomic operation, one request instead of two).

## Settings Dialog Layout

The settings window (580x520px) contains:

**Header** (red bar with title)

**Buttons** (two rows):
```
Row 1: [Save]  [Update]  [Cancel]
Row 2: [Save & Update]  [Delete Config]
```

- **Save** — persists all form fields to settings.json and restarts the update loop
- **Update** — calls `_action_update_now()` without saving (allows testing before saving)
- **Cancel** — closes dialog without saving
- **Save & Update** — saves settings and immediately triggers an update, then closes
- **Delete Config** — removes settings.json after confirmation, resets to defaults

**Form Sections** (scrollable):
- PowerDNS Connection (API URL, API Key)
- DNS Record (Zone, Hostname, Record Type, TTL)
- Options (Check Interval, Enable/Autostart checkboxes)
- Last Status (read-only, shows last IPs and timestamp)

## Debugging

### Enable debug logging
Add to top of `dynamicdns.py`:
```python
import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)
```

Then add calls:
```python
logger.debug(f"Detected IP: {ip}")
logger.debug(f"API Response: {r.status_code} {r.text}")
```

### Test IP detection
```python
updater = PowerDNSUpdater()
print(updater._get_public_ipv4())
print(updater._get_public_ipv6())
```

### Test PowerDNS API manually
```bash
# List servers
curl -H "X-API-Key: YOUR-KEY" http://localhost:8081/api/v1/servers

# Get zone
curl -H "X-API-Key: YOUR-KEY" http://localhost:8081/api/v1/servers/localhost/zones/example.com.

# Update record (manual test)
curl -X PATCH \
  -H "X-API-Key: YOUR-KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "rrsets": [{
      "name": "home.example.com",
      "type": "A",
      "changetype": "REPLACE",
      "ttl": 3600,
      "records": [{"content": "203.0.113.45", "disabled": false}]
    }]
  }' \
  http://localhost:8081/api/v1/servers/localhost/zones/example.com.
```

### Common breakpoints

**IP detection not working?**
- Check `_get_public_ipv4()` and `_get_public_ipv6()` methods
- Test services manually:
  ```bash
  curl https://api.ipify.org              # IPv4
  curl https://api64.ipify.org            # IPv6
  ```

**PowerDNS API failing?**
- Verify API is enabled: `curl -H "X-API-Key: KEY" http://api-url:8081/api/v1/servers`
- Check API key in PowerDNS config
- Verify zone format (with/without trailing dot)
- Check hostname doesn't already include zone name (just subdomain)

**Settings not saving?**
- Verify directory: `%APPDATA%\PowerDNSUpdater\`
- Check file permissions (should be user-writable)
- Look for JSON syntax errors

## Building an Executable

### Manual build
```bash
pyinstaller --onefile --windowed \
  --name PowerDNSUpdater \
  dynamicdns.py
```

Output: `dist\PowerDNSUpdater.exe`

### Using build-powerdns.bat
```bat
build-powerdns.bat
```

## Extending the App

### Support multiple zones
Change settings structure:
```python
DEFAULT_SETTINGS = {
    'zones': [
        {
            'zone': 'example.com',
            'hostname': 'home',
            'record_type': 'A',
        },
        {
            'zone': 'example.org',
            'hostname': 'office',
            'record_type': 'A',
        }
    ],
    ...
}
```

Then loop in `_update_loop()`:
```python
for zone_config in self.settings['zones']:
    ip = self._get_public_ipv4()
    self._do_pdns_update(zone_config['record_type'], ip, zone_config)
```

### Add email notifications
```python
def _send_email(self, subject: str, body: str):
    import smtplib
    from email.mime.text import MIMEText
    
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = self.settings['smtp_from']
    msg['To'] = self.settings['smtp_to']
    
    with smtplib.SMTP(self.settings['smtp_host']) as server:
        server.send_message(msg)
```

Then call after successful update:
```python
if r.status_code == 204:
    self._send_email(f'DNS Updated: {hostname}', f'IP changed to {ip}')
```

### Add webhook support
```python
def _post_webhook(self, ip: str, record_type: str):
    webhook_url = self.settings.get('webhook_url')
    if webhook_url:
        payload = {
            'hostname': self.settings['hostname'],
            'zone': self.settings['zone'],
            'record_type': record_type,
            'ip': ip,
            'timestamp': time.time()
        }
        requests.post(webhook_url, json=payload, timeout=10)
```

### Add HTTPS certificate validation
```python
# In _do_pdns_update():
r = requests.patch(
    url, json=rrsets, headers=headers, timeout=15,
    verify=self.settings.get('verify_ssl', True)  # Add CA bundle path here
)
```

### Add retry logic
```python
def _do_pdns_update_with_retry(self, record_type: str, ip: str, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            return self._do_pdns_update(record_type, ip)
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                self._set_status(f'Retry {attempt + 1} in {wait_time}s...')
                time.sleep(wait_time)
            else:
                raise
```

### Add DNS propagation check
```python
def _verify_update(self, hostname: str, ip: str) -> bool:
    import socket
    try:
        resolved = socket.gethostbyname(hostname)
        return resolved == ip
    except Exception:
        return False
```

## Testing

Create `test_powerdns.py`:

```python
import unittest
from dynamicdns import PowerDNSUpdater

class TestIPValidation(unittest.TestCase):
    def test_valid_ipv4(self):
        self.assertTrue(PowerDNSUpdater._is_valid_ipv4('192.168.1.1'))
        self.assertFalse(PowerDNSUpdater._is_valid_ipv4('256.1.1.1'))
        self.assertFalse(PowerDNSUpdater._is_valid_ipv4('not.an.ip'))

    def test_valid_ipv6(self):
        self.assertTrue(PowerDNSUpdater._is_valid_ipv6('2001:db8::1'))
        self.assertFalse(PowerDNSUpdater._is_valid_ipv6('not::an::ip'))

if __name__ == '__main__':
    unittest.main()
```

Run:
```bash
python -m unittest test_powerdns.py -v
```

## Known Limitations

1. **API Key plaintext** — use file permissions to restrict access
2. **HTTP by default** — enable HTTPS on PowerDNS API for untrusted networks
3. **Single zone only** — could support multiple zones simultaneously
4. **No DNSSEC handling** — doesn't sign records after update
5. **No zone validation** — assumes zone exists (catches errors gracefully)
6. **No batch updates** — one record per update (could batch multiple)

## Performance

- **Memory:** ~30-40 MB (Python + tkinter + pystray)
- **CPU:** <1% idle, brief spike during updates
- **Disk I/O:** Only writes JSON when IP changes
- **Network:** One PATCH request per interval (typically 200-300 bytes)

## Security Considerations

1. **API Key stored plaintext** — restrict `settings.json` permissions
2. **HTTP is default** — configure HTTPS if exposed to untrusted networks
3. **User-Agent headers** — identify the updater (intentional for audit)
4. **No credential validation** — trusts PowerDNS authentication completely
5. **Records are public** — any API call can see all zone records

---

**Last updated:** 2026-04-16
