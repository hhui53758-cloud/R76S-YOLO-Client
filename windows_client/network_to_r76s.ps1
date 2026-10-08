$ErrorActionPreference = "Stop"
$LogPath = Join-Path $PSScriptRoot "network_switch_last.log"

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Administrator)) {
    $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $arguments
    exit 0
}

try {
    Set-Content -LiteralPath $LogPath -Value "R76S network switch started: $(Get-Date -Format o)" -Encoding UTF8
    $adapters = @(
        Get-NetAdapter -Physical |
            Where-Object {
                $_.Status -ne "Not Present" -and
                $_.InterfaceDescription -notmatch "(?i)Wi-?Fi|Wireless|WLAN|802\.11|Bluetooth"
            } |
            Sort-Object @{Expression = { if ($_.Status -eq "Up") { 0 } else { 1 } }}, ifIndex
    )
    if ($adapters.Count -eq 0) {
        throw "No physical Ethernet adapter was found."
    }

    $adapter = $adapters[0]
    Add-Content -LiteralPath $LogPath -Value "Selected adapter: $($adapter.Name) [$($adapter.InterfaceDescription)] index=$($adapter.ifIndex) status=$($adapter.Status)"
    Write-Host "Selected Ethernet adapter: $($adapter.Name) [$($adapter.InterfaceDescription)]"
    Enable-NetAdapter -Name $adapter.Name -Confirm:$false
    Start-Sleep -Seconds 2

    Set-NetIPInterface -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -Dhcp Disabled
    Get-NetRoute -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.NextHop -ne "0.0.0.0" } |
        Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue
    Get-NetIPAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object IPAddress -ne "192.168.137.1" |
        Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue

    $existing = Get-NetIPAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object IPAddress -eq "192.168.137.1"
    if (-not $existing) {
        New-NetIPAddress -InterfaceIndex $adapter.ifIndex -IPAddress "192.168.137.1" -PrefixLength 24 | Out-Null
    }
    Set-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -ResetServerAddresses

    Write-Host ""
    Write-Host "R76S network is ready."
    Write-Host "PC:   192.168.137.1/24"
    Write-Host "R76S: 192.168.137.47"
    Write-Host ""
    if (Test-Connection -ComputerName "192.168.137.47" -Count 2 -Quiet) {
        Write-Host "R76S replied successfully." -ForegroundColor Green
        Add-Content -LiteralPath $LogPath -Value "Result: success; R76S replied."
    } else {
        Write-Host "No ping reply yet. Check power, SYS LED, and LAN cable." -ForegroundColor Yellow
        Add-Content -LiteralPath $LogPath -Value "Result: network configured; no ping reply."
    }
    Start-Sleep -Seconds 4
    exit 0
} catch {
    Write-Host "Network switch failed: $($_.Exception.Message)" -ForegroundColor Red
    Add-Content -LiteralPath $LogPath -Value "Result: failed"
    Add-Content -LiteralPath $LogPath -Value ($_ | Out-String)
    exit 1
}
