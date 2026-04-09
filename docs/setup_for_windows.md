# WINDOWS.md

This file provides instructions for setting up the Docker container on Windows. If you do not already have Windows Subsystem for Linux (WSL) installed and KVM enabled, please follow the steps below.

# Install WSL

```bash
wsl --install  # Installs WSL with default configuration
```
# Enable KVM

```bash
wsl -d Ubuntu # Open Ubuntu
sudo usermod -a -G kvm ${USER} # Add yourself to KVM group
```

Add these two sections to the /etc/wsl.conf file:

[boot]
command = /bin/bash -c 'chown -v root:kvm /dev/kvm && chmod 660 /dev/kvm'

[wsl2]
nestedVirtualization = true

# Next steps

After installing WSL and KVM, you may need to restart your computer. Otherwise, the Docker container should be able to be built using WSL now.


