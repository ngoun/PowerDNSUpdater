# PowerDNS Dynamic IP Updater

A lightweight Windows system tray application for automatic PowerDNS record updates. Updates A/AAAA records in your self-hosted PowerDNS authoritative server when your public IP changes.

## Features

- **System Tray Integration** — runs in the background, accessible from Windows notification area
- **Automatic Updates** — periodically checks your public IP and updates your PowerDNS records
- **Smart Detection** — only sends updates to PowerDNS when your IP actually changes
- **Settings GUI** — configure PowerDNS server, zone, hostname, and API key from an intuitive dialog
- **IPv4 & IPv6 Support** — update A records (IPv4) or AAAA records (IPv6)
- **Autostart** — option to launch automatically when Windows starts
- **Status Monitoring** — real-time status in the tray tooltip showing last IPs and update time
- **Resilient IP Detection** — uses multiple fallback services to detect your public IP
- **Custom TTL** — configure the TTL for updated records

## Requirements

- **PowerDNS Authoritative Server** with API enabled
- PowerDNS API accessible (typically `http://localhost:8081`)
- Valid PowerDNS API key
- A zone and hostname to update

## Installation

### Option 1: Run from Source (requires Python 3.7+)

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the app:**
   ```bash
   python dynamicdns.py
   ```

### Option 2: Use the Standalone Executable

1. **Build an `.exe`:**
   ```bash
   build.bat
   ```
   This generates `dist\PowerDNSUpdater.exe` — a single-file executable with no Python required.

2. **Run it:**
   Double-click `PowerDNSUpdater.exe` and it starts minimized in the system tray.

## Configuration

### PowerDNS Setup

First, ensure PowerDNS API is enabled. In `pdns.conf` or `pdns.local.conf`:

```ini
api=yes
api-key=your-secret-api-key-here
api-url=0.0.0.0
```

Then restart PowerDNS:
```bash
sudo systemctl restart pdns
```

### First Time Setup

1. Click the tray icon → **Settings…**
2. Fill in PowerDNS connection:
   - **API URL** — where PowerDNS API runs (e.g., `http://192.168.1.10:8081`)
   - **API Key** — your PowerDNS API key (from `pdns.conf`)
3. Fill in DNS record details:
   - **Zone** — the zone name (e.g., `example.com` or `example.com.`)
   - **Hostname** — the record to update (e.g., `home` for `home.example.com`, or leave blank for zone apex)
   - **Record Type** — `A` (IPv4), `AAAA` (IPv6), or `BOTH` (update both records simultaneously)
   - **TTL** — time-to-live in seconds (default 3600)
4. Configure options:
   - **Check Interval** — how often to check IP (in seconds, minimum 60)
   - **Enable automatic updates** — start monitoring immediately
   - **Start with Windows** — autostart on boot (optional)
5. Click **Save** or **Save & Update Now**

### Settings Location

Settings are saved to:
```
%APPDATA%\PowerDNSUpdater\settings.json
```

Example on Windows:
```
C:\Users\YourUsername\AppData\Roaming\PowerDNSUpdater\settings.json
```

Example settings file:
```json
{
  "pdns_url": "http://192.168.1.10:8081",
  "api_key": "your-secret-key",
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

## How It Works

1. **IP Detection** — Every N seconds (configurable), the app detects your public IP:
   - For **A records**: IPv4 from `api.ipify.org`, `icanhazip.com`, etc.
   - For **AAAA records**: IPv6 from `api64.ipify.org`, etc.
   - For **BOTH records**: IPv4 and IPv6 are detected simultaneously

2. **Change Detection** — Compares against the last recorded IP:
   - If **same**: logs "unchanged" and waits for next interval
   - If **different**: proceeds to update

3. **DNS Update** — Sends PATCH request to PowerDNS API:
   ```
   PATCH http://{api_url}/api/v1/servers/localhost/zones/{zone}.
   X-API-Key: {api_key}
   Content-Type: application/json

   {
     "rrsets": [{
       "name": "home.example.com",
       "type": "A",
       "changetype": "REPLACE",
       "ttl": 3600,
       "records": [{"content": "203.0.113.45", "disabled": false}]
     }]
   }
   ```

4. **Response Handling**:
   - `204 No Content` — update successful
   - `401 Unauthorized` — invalid API key
   - `404 Not Found` — zone or hostname not found
   - `400 Bad Request` — malformed request (check hostname format)
   - Other — HTTP error with details

5. **Status Update** — Tooltip shows:
   - Current status (updated, unchanged, error)
   - Last successful IPv4 and IPv6 addresses
   - Last update timestamp

## Tray Menu

Right-click the tray icon for:

- **Status: [current status]** — informational only
- **Update Now** — force an immediate IP check and update
- **Settings…** — open the configuration dialog
- **Quit** — gracefully shut down the application

## Settings Dialog Buttons

The settings window has five action buttons organized in two rows:

**Row 1 (Top):**
- **Save** — save settings and apply them
- **Update** — immediately check IP and update DNS (without saving settings)
- **Cancel** — close without saving

**Row 2 (Bottom):**
- **Save & Update** — save settings and immediately check IP and update DNS
- **Delete Config** — remove all saved configuration (cannot be undone, requires confirmation)

## Troubleshooting

### "Not configured" error
- Open Settings and fill in zone, hostname, API URL, and API key
- Ensure "Enable automatic updates" is checked

### "Error: invalid API key"
- Double-check your API key in PowerDNS config
- Verify PowerDNS was restarted after config change
- Confirm API is enabled in `pdns.conf`: `api=yes`

### "Error: zone or hostname not found"
- Confirm the zone exists in PowerDNS: `pdnsutil list-zones`
- Check zone name format (with or without trailing dot)
- Verify hostname syntax:
  - For apex (`example.com`): leave hostname **blank**
  - For subdomain (`home.example.com`): enter `home`
- Use `pdnsutil get-zone example.com` to see existing records

### "Error: cannot reach PowerDNS server"
- Verify PowerDNS is running: `systemctl status pdns`
- Check API URL is correct (with port 8081)
- Ensure network connectivity to PowerDNS server
- Verify firewall allows access to API port

### "Error: bad request (400)"
- Check hostname format — use just the subdomain part, not FQDN
- Verify record type (A or AAAA) matches your IP type
- Check TTL is a valid number (60+)

### IP updates aren't working
1. Open Settings and click **Save & Update Now** to test
2. Check the status in the tray tooltip
3. Verify the record updated in PowerDNS:
   ```bash
   pdnsutil get-zone example.com | grep home
   ```
4. Check PowerDNS API is accessible:
   ```bash
   curl -H "X-API-Key: YOUR_KEY" http://localhost:8081/api/v1/servers/localhost
   ```

## Security Notes

- **API Key is stored in plain text** in `settings.json` with default Windows permissions
- Restrict access to `%APPDATA%\PowerDNSUpdater\settings.json` if other users access your machine
- Consider creating a **separate API user** in PowerDNS (if supported) with limited permissions
- The app uses **HTTP by default** — configure HTTPS on your PowerDNS API if exposed to untrusted networks
- User-Agent headers identify the updater for audit trails

## Advanced: PowerDNS API Details

This app uses the **PowerDNS HTTP API v1**:

```
Method: PATCH
Endpoint: https://{api_url}/api/v1/servers/localhost/zones/{zone}.
Headers:
  - X-API-Key: {api_key}
  - Content-Type: application/json
Body:
  {
    "rrsets": [
      {
        "name": "{fqdn}",
        "type": "A" or "AAAA",
        "changetype": "REPLACE",
        "ttl": {ttl},
        "records": [
          {
            "content": "{ip_address}",
            "disabled": false
          }
        ]
      }
    ]
  }
```

Reference: https://doc.powerdns.com/authoritative/http-api/zone.html

## Building an Executable

### Requirements
- Python 3.7+ installed
- PyInstaller: `pip install pyinstaller`

### Build process
```bash
build.bat
```

This:
1. Installs/updates dependencies
2. Runs PyInstaller to bundle everything into `dist\PowerDNSUpdater.exe`
3. Output is a single executable file (~60 MB) with no external dependencies

## License

No specific license. Use freely.

## Support

If you encounter issues:
1. Check the troubleshooting section above
2. Verify PowerDNS is running and API is enabled
3. Test API connectivity: `curl -H "X-API-Key: KEY" http://api-url:8081/api/v1/servers`
4. Check `%APPDATA%\PowerDNSUpdater\settings.json` for saved configuration
5. Try clicking "Update Now" to force an immediate check
6. Look at the status tooltip for error messages

---

**Version:** 1.0  
**Last Updated:** 2026-04-16
