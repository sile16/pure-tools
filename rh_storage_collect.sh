#!/bin/bash

# Collection tool, creates a timestamped tar file and adds each file in, as well as each script output
# Purpose: collect relevant information to troubleshoot Fibre Channel SAN / Storage configuration / Perf issues.

timestamp=$(date +%Y%m%d%H%M%S)
current_dir=$(pwd)
collection_dir="$current_dir/output/rh_collect_${timestamp}"
log_file="${collection_dir}/collection_log_${timestamp}.txt"

# Create collection directory
mkdir -p $collection_dir

# Start collection log
echo "$(date) - Starting collection" > $log_file

files_to_collect=(
  '/etc/multipath.conf'
  '/etc/udev/rules.d/99-pure-storage.rules'
  '/etc/redhat-release'
  '/sys/class/fc_host/host*/statistics/*'
  '/sys/class/fc_host/host*/speed'
  '/sys/class/fc_host/host*/port_state'
  '/sys/class/fc_host/host*/port_id'
  '/sys/class/fc_host/host*/fc4_stats'
  '/sys/block/sd*/queue/scheduler'
  '/sys/block/sd*/device/inquiry'
  #NVME
  '/etc/nvme/hostnqn'
  '/etc/nvme/hostid'
  '/etc/nvme/discovery.conf'
)

cmds_to_run=(
  'uname -a'
  'multipath -ll'
  'multipath_wwn_map.sh'
  'df -hP'
  'mount'
  "dmesg | grep -i 'error\|fail\|warn'"
  #NVME
  'nvme list'
  'nvme list-subsys'
  'nvme show-hostnqn'
  'nvme show-ctrl'
)

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
  cmd_file=$(echo $cmd | tr ' /' '__').txt
  echo "$(date) - Running command: $cmd" >> $log_file
  eval $cmd >> "${collection_dir}/${cmd_file}" 2>> $log_file
done

# Create tar.gz archive
tar -czf "${collection_dir}.tar.gz" -C "$current_dir/output/" "rh_collect_${timestamp}"

# Output the final tar.gz file name
echo "Collection file: ./output/rh_collect_${timestamp}.tar.gz"


