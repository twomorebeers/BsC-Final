proxmox_api_url          = "https://pve-node-1:8006/api2/json"
proxmox_api_token_id     = "terraform@pam!soho-iac"
proxmox_api_token_secret = "a7c9def1-1f2f-4bf2-8591-7a7b9d8ddcd5"

proxmox_node       = "pve-node-1"
lxc_vmid           = 210
lxc_hostname       = "soho-docker"
ostemplate         = "local:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst"
rootfs_storage     = "local-lvm"
rootfs_size        = "20G"
bridge             = "vmbr0"
# NOTE: lxc_ip should match ansible/inventory.ini host IP
lxc_ip             = "192.168.1.69/24"
gateway            = "192.168.1.1"
lxc_root_password  = "REPLACE_WITH_STRONG_PASSWORD"
ssh_public_key_path = "/Users/bogdishor/.ssh/id_ed25519.pub"
proxmox_tls_insecure = true
