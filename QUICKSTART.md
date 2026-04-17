# PowerDNS Dynamic IP Updater — Quick Start

Get your DNS record updating automatically in 5 minutes.

## Step 1: Enable PowerDNS API

SSH into your PowerDNS server and edit the config:

```bash
sudo nano /etc/powerdns/pdns.local.conf
```

Add or uncomment:
```ini
api=yes
api-key=your-super-secret-key-here
api-url=0.0.0.0:8081
```

Restart PowerDNS:
```bash
sudo systemctl restart pdns
```

Verify it's working:
```bash
curl -H "X-API-Key: your-super-secret-key-here" http://localhost:8081/api/v1/servers
```

## Step 2: Install the App

### Quick: Run from Python
```bash
pip install -r requirements.txt
python dynamicdns.py
```

### Standalone: Build the .exe
```bash
build.bat
# Run: dist\PowerDNSUpdater.exe
```

## Step 3: Configure

1. **Tray icon appears** → right-click it
2. Click **Settings…**
3. Fill in:
   - **API URL:** `http://192.168.1.10:8081` (your PowerDNS server)
   - **API Key:** the key you set in `pdns.local.conf`
   - **Zone:** `example.com` (the domain to update)
   - **Hostname:** `home` (the subdomain, e.g., `home.example.com`)
   - **Record Type:** `A` (IPv4), `AAAA` (IPv6), or `BOTH` (update both simultaneously)
   - **TTL:** `3600` (or whatever you prefer)
4. Check **Enable automatic updates**
5. Check **Start with Windows** (optional)
6. Click **Save & Update** to save and test, or click **Update** to test first without saving

## Step 4: Verify

1. Check the tray icon tooltip → should show "Updated A → {your-ip}"
2. Verify in PowerDNS:
   ```bash
   pdnsutil get-zone example.com | grep home
   ```
3. Optional: change network (VPN, mobile hotspot) → should auto-update

## Common Issues

| Issue | Fix |
|-------|-----|
| "Cannot reach PowerDNS server" | Check API URL (with port 8081), verify firewall |
| "Invalid API key" | Verify key in `pdns.local.conf`, restart PowerDNS |
| "Zone not found" | Check zone exists: `pdnsutil list-zones` |
| "Bad request (400)" | Verify hostname format: just the subdomain, not FQDN |

## API URL Examples

| Setup | API URL |
|-------|---------|
| Local (same machine) | `http://localhost:8081` |
| Local network | `http://192.168.1.10:8081` |
| Remote (HTTPS) | `https://dns.example.com:8081` |

## Next Steps

- Read [README.md](README.md) for full documentation
- Enable "Start with Windows" for automatic startup
- Test by forcing an update: Settings → Save & Update Now
- Monitor the tray tooltip for status

---

**Need help?** See [README.md](README.md) troubleshooting section.
