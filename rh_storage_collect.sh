#!/bin/bash

# Collection tool, creates a timestamped tar file and adds each file in, as well as each script output
# Purpose: collect relevant information to troubleshoot Fibre Channel SAN / Storage configuration / Perf issues,
# and to aid in planning an LVM-based data migration.

timestamp=$(date +%Y%m%d%H%M%S)
current_dir=$(pwd)
collection_dir="$current_dir/output/rh_collect_${timestamp}"
log_file="${collection_dir}/collection_log_${timestamp}.txt"

# Create collection directory
mkdir -p "$collection_dir"

# Start collection log
echo "$(date) - Starting collection" > "$log_file"

files_to_collect=(
  '/etc/multipath.conf'
  '/etc/udev/rules.d/99-pure-storage.rules'
  '/etc/redhat-release'
  '/etc/SuSE-release'
  '/sys/class/fc_host/host*/statistics/*'
  '/sys/class/fc_host/host*/speed'
  '/sys/class/fc_host/host*/port_state'
  '/sys/class/fc_host/host*/port_id'
  '/sys/class/fc_host/host*/fc4_stats'
  '/sys/block/sd*/queue/scheduler'
  '/sys/block/sd*/device/inquiry'
  # NVMe
  '/etc/nvme/hostnqn'
  '/etc/nvme/hostid'
  '/etc/nvme/discovery.conf'
  # LVM
  '/etc/lvm/lvm.conf'
  '/etc/fstab'
  '/proc/partitions'
)

cmds_to_run=(
  'uname -a'
  'multipath -ll'
  'multipath_wwn_map.sh'
  'df -hP'
  'mount'
  "dmesg | grep -i 'error\|fail\|warn'"
  # NVMe
  'nvme list'
  'nvme list-subsys'
  'nvme show-hostnqn'
  'nvme show-ctrl'
  # LVM and disk info
  'fdisk -l'
  'parted -l'
  'pvdisplay'
  'pvdisplay -v'
  'vgdisplay'
  'vgdisplay -v'
  'lvdisplay'
  'lvdisplay -m'
  'pvs'
  'vgs'
  'lvs'
  'lvs -a -o +devices'
  'blkid'
  'lsblk -f'
  'cat /etc/fstab'
  'dmsetup ls --tree'
  'dmsetup table'
  'ls -l /dev/disk/by-id/'
)

# Function to generate a safe filename from a command
generate_safe_filename() {
  echo "$1" | sed 's/[^A-Za-z0-9._-]/_/g'
}

# Collect all the files
for file_pattern in "${files_to_collect[@]}"; do
  for file in $file_pattern; do
    if [ -e "$file" ]; then
      echo "$(date) - Adding $file" >> "$log_file"
      cp --parents "$file" "$collection_dir" 2>> "$log_file"
    else
      echo "$(date) - File $file does not exist" >> "$log_file"
    fi
  done
done

# Collect all the command outputs
for cmd in "${cmds_to_run[@]}"; do
  cmd_file=$(generate_safe_filename "$cmd").txt
  echo "$(date) - Running command: $cmd" >> "$log_file"
  if command -v ${cmd%% *} &> /dev/null; then
    eval $cmd >> "${collection_dir}/${cmd_file}" 2>> "$log_file"
  else
    echo "$(date) - Command not found: ${cmd%% *}" >> "$log_file"
  fi
done

# Create tar.gz archive
tar -czf "${collection_dir}.tar.gz" -C "$current_dir/output/" "rh_collect_${timestamp}"

# Output the final tar.gz file name
echo "Collection file: ./output/rh_collect_${timestamp}.tar.gz"
