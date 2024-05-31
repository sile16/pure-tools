#!/bin/bash

# Iterate over each line of the multipath -ll output
# example line:  1:0:3:1 sdaf 65;240 active ready running
multipath -ll | while read line; do
    # Check if the line contains a path in the form of 'host:channel:id:lun'
    if [[ $line =~ ([0-9]+:[0-9]+:[0-9]+:[0-9]+) ]]; then
        # Extract the entire SCSI path
        scsi_path=${BASH_REMATCH[0]}
        block_device=${BASH_REMATCH[1]}

        # Retrieve the host number for host WWN lookup
        host_number=$(echo "$scsi_path" | cut -d ':' -f 1)
        host_wwn_path="/sys/class/fc_host/host${host_number}/port_name"
        if [ -f "$host_wwn_path" ]; then
            host_wwn=$(cat "$host_wwn_path" | tr '[:lower:]' '[:upper:]')
            host_wwn=${host_wwn#0X}
        else
            host_wwn="Unknown"
        fi

        # Use lsscsi to get the target port WWN and convert it to uppercase
        target_wwn=$(lsscsi -t --list [$scsi_path] | grep 'port_name=' | cut -d '=' -f 2 | tr '[:lower:]' '[:upper:]')
        target_wwn=${target_wwn#0X}

        # if blank, change to Uknown
        [[ -z "$target_wwn" ]] && target_wwn="Unknown"

        

        # Append host and target WWN information to the line
        line="${line}, Host: $host_wwn, Target: $target_wwn"
    fi
    # Print the line
    echo $line
done