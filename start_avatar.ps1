# Avatar Studio — to'liq ishga tushirish (Windows logon'da avtomatik).
# 1) WSL backend'ni supervisor ostida (qulasa qayta ishga tushadi) ajratib ishga tushiradi.
# 2) WSL IP'ni olib LAN port-forward (portproxy) + firewall'ni tiklaydi.
# ADMIN kerak (portproxy/firewall uchun). Logon vazifasi 'highest' bilan ishlaydi.
$ErrorActionPreference = 'SilentlyContinue'
$distro = 'Ubuntu-24.04'
$port = 8100

# --- 1) Backend (agar ishlamayotgan bo'lsa) ---
$running = (wsl -d $distro -- bash -lc "pgrep -f 'uvicorn app.main' >/dev/null && echo yes || echo no").Trim()
if ($running -ne 'yes') {
    Start-Process -WindowStyle Hidden wsl -ArgumentList '-d',$distro,'--','bash','-lc',`
      'cd /mnt/c/Users/User/Desktop/Avatar_Studio && setsid bash backend/serve_forever.sh >> /tmp/avatar_backend.log 2>&1 < /dev/null'
    Start-Sleep 20
}

# --- 2) Port-forward + firewall (WSL IP restart'da o'zgaradi) ---
$wslip = (wsl -d $distro -- bash -lc "ip -4 addr show eth0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}'").Trim()
if ($wslip) {
    netsh interface portproxy delete v4tov4 listenport=$port listenaddress=0.0.0.0 2>$null | Out-Null
    netsh interface portproxy add v4tov4 listenport=$port listenaddress=0.0.0.0 connectport=$port connectaddress=$wslip | Out-Null
    netsh advfirewall firewall delete rule name="Avatar Studio $port" 2>$null | Out-Null
    netsh advfirewall firewall add rule name="Avatar Studio $port" dir=in action=allow protocol=TCP localport=$port | Out-Null
}
$lan = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -eq 'Ethernet' } | Select-Object -First 1).IPAddress
Write-Output "Backend + LAN tayyor."
Write-Output "LAN URL:       https://$lan`:$port"
Write-Output "Tailscale URL: https://100.114.162.27`:$port"
