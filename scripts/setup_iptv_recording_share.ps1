param(
    [string]$HostAlias = "hp290",
    [string]$VmAlias = "iptv-vm01",
    [string]$VmLanIp = "192.168.1.67",
    [string]$HomeGateway = "192.168.1.1",
    [string]$TrailerSubnet = "192.168.2.0/24",
    [string]$HostLanDevice = "enp2s0",
    [string]$LanMac = "52:54:00:67:01:67",
    [string]$ShareName = "TiviMate_Recordings",
    [string]$ShareUser = "tivimate",
    [string]$SharePassword = $env:IPTV_RECORDING_SHARE_PASSWORD,
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($SharePassword)) {
    throw "Provide -SharePassword or set IPTV_RECORDING_SHARE_PASSWORD before running this script."
}

function Invoke-Ssh {
    param(
        [Parameter(Mandatory = $true)][string]$Target,
        [Parameter(Mandatory = $true)][string]$Command
    )

    $output = & ssh -o BatchMode=yes -o ConnectTimeout=12 $Target $Command 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "ssh $Target failed: $output"
    }
    return $output
}

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message"
}

$recordingRoot = "/srv/iptv-serverbridge/recordings"
$lanCidr = "$VmLanIp/24"

Write-Step "Checking HP host and VM access"
Invoke-Ssh $HostAlias "hostname; hostname -I" | Write-Output
Invoke-Ssh $VmAlias "hostname; hostname -I; sudo -n true && echo sudo_ok" | Write-Output

if (-not $ValidateOnly) {
    Write-Step "Ensuring VM has a LAN interface on $VmLanIp"
    $attachCommand = @"
set -euo pipefail
if sudo -n virsh domiflist iptv-vm01 | grep -qi '$LanMac'; then
  echo 'LAN interface already present: $LanMac'
else
  sudo -n virsh attach-interface --domain iptv-vm01 --type direct --source '$HostLanDevice' --model virtio --mac '$LanMac' --config --live
  echo 'Attached LAN interface: $LanMac'
fi
sudo -n virsh domiflist iptv-vm01
"@
    Invoke-Ssh $HostAlias $attachCommand | Write-Output

    Write-Step "Applying VM netplan for LAN and trailer VPN routing"
    $netplanCommand = @"
set -euo pipefail
sudo -n cp -a /etc/netplan/99-iptv-vm01-lan-recordings.yaml /etc/netplan/99-iptv-vm01-lan-recordings.yaml.bak.`$(date +%Y%m%d_%H%M%S) 2>/dev/null || true
sudo -n tee /etc/netplan/99-iptv-vm01-lan-recordings.yaml >/dev/null <<'EOF'
network:
  version: 2
  ethernets:
    enp1s0:
      dhcp4: true
      dhcp4-overrides:
        route-metric: 200
      dhcp6: false
      optional: true
    lan0:
      match:
        macaddress: "$LanMac"
      set-name: "lan0"
      addresses:
        - $lanCidr
      routes:
        - to: default
          via: $HomeGateway
          metric: 50
        - to: $TrailerSubnet
          via: $HomeGateway
          metric: 10
      nameservers:
        addresses:
          - $HomeGateway
          - 1.1.1.1
      optional: true
EOF
sudo -n chmod 600 /etc/netplan/*.yaml
sudo -n netplan generate
sudo -n netplan apply
sleep 3
ip -br addr
ip route
"@
    Invoke-Ssh $VmAlias $netplanCommand | Write-Output

    Write-Step "Installing and configuring Samba share inside the VM"
    $sambaCommand = @"
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
sudo -n apt-get update
sudo -n apt-get install -y samba smbclient acl
sudo -n install -d -o andrew -g andrew -m 2775 '$recordingRoot'
sudo -n install -d -o andrew -g andrew -m 2775 '$recordingRoot/tivimate' '$recordingRoot/tvheadend' '$recordingRoot/test'
sudo -n setfacl -R -m u:andrew:rwx,g:andrew:rwx '$recordingRoot'
sudo -n setfacl -R -d -m u:andrew:rwx,g:andrew:rwx '$recordingRoot'
if ! id '$ShareUser' >/dev/null 2>&1; then
  sudo -n useradd --system --no-create-home --shell /usr/sbin/nologin --gid andrew '$ShareUser'
fi
printf '%s\n%s\n' '$SharePassword' '$SharePassword' | sudo -n smbpasswd -a -s '$ShareUser' >/dev/null
sudo -n smbpasswd -e '$ShareUser' >/dev/null
sudo -n cp -a /etc/samba/smb.conf /etc/samba/smb.conf.bak.`$(date +%Y%m%d_%H%M%S)
sudo -n python3 - <<'PY'
from pathlib import Path
path = Path('/etc/samba/smb.conf')
text = path.read_text()
start = '# >>> IPTV RECORDINGS SHARE START'
end = '# <<< IPTV RECORDINGS SHARE END'
block = '''# >>> IPTV RECORDINGS SHARE START
[global]
   netbios name = IPTV-VM01
   server string = IPTV VM recordings server
   server min protocol = SMB2
   server max protocol = SMB3
   map to guest = never

[$ShareName]
   comment = Shared IPTV recordings for TiviMate and Tvheadend
   path = $recordingRoot
   browseable = yes
   read only = no
   guest ok = no
   valid users = $ShareUser andrew
   force user = andrew
   force group = andrew
   create mask = 0664
   directory mask = 2775
   inherit permissions = yes
   veto files = /.DS_Store/Thumbs.db/
# <<< IPTV RECORDINGS SHARE END
'''
if start in text and end in text:
    before = text.split(start, 1)[0].rstrip() + '\n\n'
    after = text.split(end, 1)[1].lstrip()
    text = before + block + '\n' + after
else:
    text = text.rstrip() + '\n\n' + block
path.write_text(text)
PY
sudo -n testparm -s >/tmp/iptv_samba_testparm.txt
sudo -n systemctl enable --now smbd nmbd
sudo -n systemctl restart smbd nmbd
sudo -n testparm -s 2>/dev/null | sed -n '/\[$ShareName\]/,/^\[/p'
systemctl is-active smbd nmbd
"@
    Invoke-Ssh $VmAlias $sambaCommand | Write-Output
}

Write-Step "Validating VM and LAN SMB access"
Invoke-Ssh $VmAlias "ip -br addr; ip route get 192.168.2.1; smbclient -L //127.0.0.1 -U '$ShareUser%$SharePassword' -m SMB3 | sed -n '1,80p'" | Write-Output

$port445 = Test-NetConnection -ComputerName $VmLanIp -Port 445 -InformationLevel Quiet -WarningAction SilentlyContinue
if (-not $port445) {
    throw "Windows cannot reach SMB on $VmLanIp:445"
}

$root = "\\$VmLanIp\$ShareName"
try {
    Remove-SmbMapping -RemotePath $root -Force -UpdateProfile:$false -ErrorAction SilentlyContinue | Out-Null
} catch {
}

New-SmbMapping -RemotePath $root -UserName $ShareUser -Password $SharePassword -Persistent:$false -ErrorAction Stop | Out-Null
$testDir = Join-Path $root "test"
New-Item -ItemType Directory -Path $testDir -Force | Out-Null
$testFile = Join-Path $testDir "x1_setup_script_test.txt"
Set-Content -Path $testFile -Value ("x1 setup script validation " + (Get-Date).ToString("s")) -Encoding ASCII
Get-Content $testFile | Write-Output
Remove-Item $testFile -Force
Remove-SmbMapping -RemotePath $root -Force -UpdateProfile:$false

Write-Step "Validation complete"
Write-Output "Server name: IPTV-VM01"
Write-Output "LAN IP: $VmLanIp"
Write-Output "SMB path: \\$VmLanIp\$ShareName"
Write-Output "User: $ShareUser"
