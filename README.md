# pure-tools
Tools for Pure Storage

# rh_collect_storage_diag.sh
Collects config files and runs commands to help validate storage configuration and help diagnose certain environmental / external issues that maybe affecting performance or functionality.


## Usage:
``` 
# git clone https://github.com/sile16/pure-tools.git
# cd pure-tools/
# ./rh_collect_storage_diag.sh
```

# multpath_wwn_map.sh
This runs the standard multipath -ll command but also maps each 'sd' device to the source HBA WWN and Target WWN and shown in the output.

# Docker
Used for testing the script

# test.sh
Build the docker image and run a test
