# Avatar Studio — WSL backend'ni LAN'ga chiqarish (port 8100).
# WSL IP restart'da o'zgaradi — bu skript joriy WSL IP'ni olib port-forward'ni yangilaydi.
# ADMIN PowerShell'da ishga tushiring:  powershell -ExecutionPolicy Bypass -File set_lan.ps1
$port = 8100
$wslip = (wsl -d Ubuntu-24.04 -- bash -lc "ip -4 addr show eth0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}'").Trim()
if (-not $wslip) { Write-Output "WSL IP topilmadi"; exit 1 }
netsh interface portproxy delete v4tov4 listenport=$port listenaddress=0.0.0.0 2>$null | Out-Null
netsh interface portproxy add v4tov4 listenport=$port listenaddress=0.0.0.0 connectport=$port connectaddress=$wslip
netsh advfirewall firewall delete rule name="Avatar Studio $port" 2>$null | Out-Null
netsh advfirewall firewall add rule name="Avatar Studio $port" dir=in action=allow protocol=TCP localport=$port | Out-Null
$lan = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -eq 'Ethernet' } | Select-Object -First 1).IPAddress
Write-Output "Port-forward yangilandi: 0.0.0.0:$port -> $wslip`:$port"
Write-Output "LAN URL:       https://$lan`:$port   (mikrofon uchun HTTPS shart!)"
Write-Output "Tailscale URL: https://100.114.162.27`:$port (agar Tailscale ulangan bo'lsa)"
Write-Output "Eslatma: o'z-imzoli sertifikat — brauzer ogohlantiradi, 'Advanced -> Proceed' bosing."
