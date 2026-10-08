$ErrorActionPreference = "Stop"
$LogPath = Join-Path $PSScriptRoot "network_dhcp_last.log"

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Write-Log([string]$Message) {
    Add-Content -LiteralPath $LogPath -Value "$(Get-Date -Format o) $Message" -Encoding UTF8
}

function Get-PhysicalEthernet {
    return @(
        Get-NetAdapter -Physical |
            Where-Object {
                $_.Status -ne "Not Present" -and
                $_.InterfaceDescription -notmatch "(?i)Wi-?Fi|Wireless|WLAN|802\.11|Bluetooth"
            } |
            Sort-Object @{Expression = { if ($_.Status -eq "Up") { 0 } else { 1 } }}, ifIndex
    ) | Select-Object -First 1
}

function Get-WifiInterfaces {
    return @(
        Get-NetAdapter -Physical |
            Where-Object { $_.InterfaceDescription -match "(?i)Wi-?Fi|Wireless|WLAN|802\.11" }
    )
}

function Set-WifiPreferred($Ethernet, $WifiAdapters) {
    Set-NetIPInterface -InterfaceIndex $Ethernet.ifIndex -AddressFamily IPv4 -AutomaticMetric Disabled -InterfaceMetric 70
    foreach ($wifi in $WifiAdapters) {
        Set-NetIPInterface -InterfaceIndex $wifi.ifIndex -AddressFamily IPv4 -AutomaticMetric Disabled -InterfaceMetric 25 -ErrorAction SilentlyContinue
    }
}

function Add-TemporaryHostRoute([string]$Address, $Ethernet, [string]$Gateway) {
    $parsed = $null
    if (-not [Net.IPAddress]::TryParse($Address, [ref]$parsed)) {
        return $null
    }
    if ($parsed.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) {
        return $null
    }
    $prefix = "$($parsed.IPAddressToString)/32"
    Get-NetRoute -InterfaceIndex $Ethernet.ifIndex -DestinationPrefix $prefix -ErrorAction SilentlyContinue |
        Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue
    return New-NetRoute -DestinationPrefix $prefix -InterfaceIndex $Ethernet.ifIndex -NextHop $Gateway -RouteMetric 1 -PolicyStore ActiveStore
}

if (-not (Test-Administrator)) {
    $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $arguments
    exit 0
}

Set-Content -LiteralPath $LogPath -Value "Safe DHCP restore started: $(Get-Date -Format o)" -Encoding UTF8
$adapter = $null
$wifiAdapters = @()
$probeRoutes = @()

try {
    $adapter = Get-PhysicalEthernet
    if (-not $adapter) {
        throw "No physical Ethernet adapter was found."
    }
    $wifiAdapters = Get-WifiInterfaces
    Write-Log "Selected adapter: $($adapter.Name) [$($adapter.InterfaceDescription)] index=$($adapter.ifIndex)"

    Enable-NetAdapter -Name $adapter.Name -Confirm:$false
    Set-WifiPreferred $adapter $wifiAdapters

    Get-NetRoute -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.NextHop -ne "0.0.0.0" } |
        Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue
    Get-NetIPAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue
    Set-NetIPInterface -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -Dhcp Enabled
    Set-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex -ResetServerAddresses

    Start-Service Dhcp -ErrorAction SilentlyContinue
    Start-Service netprofm -ErrorAction SilentlyContinue
    Start-Service NlaSvc -ErrorAction SilentlyContinue
    Restart-NetAdapter -Name $adapter.Name -Confirm:$false

    Write-Host ""
    Write-Host "Safe normal-network mode is active." -ForegroundColor Green
    Write-Host "Wi-Fi will remain the main Internet connection."
    Write-Host "Connect the normal wired cable now. Waiting for DHCP..."

    $sourceIp = $null
    $gateway = $null
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        Start-Sleep -Seconds 3
        $config = Get-NetIPConfiguration -InterfaceIndex $adapter.ifIndex -ErrorAction SilentlyContinue
        $sourceIp = @($config.IPv4Address | Where-Object { $_.IPAddress -notlike "169.254.*" })[0].IPAddress
        $gateway = @($config.IPv4DefaultGateway)[0].NextHop
        if ($sourceIp -and $gateway) {
            break
        }
    }
    if (-not $sourceIp -or -not $gateway) {
        throw "No DHCP address was received. Check the normal wired cable and run this script again."
    }
    Write-Log "DHCP received: IP=$sourceIp gateway=$gateway; Wi-Fi remains preferred."

    $probeAddresses = @(
        Resolve-DnsName "www.msftconnecttest.com" -Type A -ErrorAction SilentlyContinue |
            Where-Object { $_.PSObject.Properties.Name -contains "IPAddress" -and $_.IPAddress } |
            Select-Object -ExpandProperty IPAddress -Unique
    )
    foreach ($address in $probeAddresses) {
        $route = Add-TemporaryHostRoute $address $adapter $gateway
        if ($route) {
            $probeRoutes += $route
        }
    }

    $headers = & curl.exe --interface $sourceIp --max-time 10 --silent --show-error --dump-header - --output NUL "http://www.msftconnecttest.com/redirect" 2>&1 | Out-String
    $locationMatch = [regex]::Match($headers, "(?im)^Location:\s*(\S+)\s*$")
    foreach ($route in $probeRoutes) {
        $route | Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue
    }
    $probeRoutes = @()

    if (-not $locationMatch.Success) {
        Write-Host "No captive-portal redirect was detected." -ForegroundColor Yellow
        Write-Host "Wi-Fi is still preferred, so Internet access remains available."
        Write-Log "No portal redirect detected; Wi-Fi remains preferred."
        Start-Sleep -Seconds 8
        exit 0
    }

    $portalUrl = $locationMatch.Groups[1].Value.Trim()
    $portalUri = [Uri]$portalUrl
    $portalRoute = Add-TemporaryHostRoute $portalUri.Host $adapter $gateway
    Write-Log "Portal URL: $portalUrl"
    if ($portalRoute) {
        Write-Log "Portal host route added through Ethernet: $($portalUri.Host) via $gateway"
    }

    Write-Host ""
    Write-Host "The real wired-network sign-in page will open now." -ForegroundColor Yellow
    Write-Host "Wi-Fi stays preferred, so other Internet apps should keep working."
    Write-Host "After sign-in, close this window. To actually use wired Internet, turn Wi-Fi off."
    Start-Process $portalUrl
    Write-Log "Result: portal opened safely; Wi-Fi remains preferred."
    Start-Sleep -Seconds 15
    exit 0
} catch {
    foreach ($route in $probeRoutes) {
        $route | Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue
    }
    try {
        if ($adapter) {
            Set-WifiPreferred $adapter $wifiAdapters
        }
    } catch {}
    Write-Host "Network restore failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Wi-Fi has been kept as the preferred connection." -ForegroundColor Yellow
    Write-Log "Result: failed; $($_ | Out-String)"
    Start-Sleep -Seconds 8
    exit 1
}
