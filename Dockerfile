# Use CentOS Stream 9 base image for amd64 architecture
FROM --platform=linux/amd64 quay.io/centos/centos:stream9

# Install necessary packages
RUN yum update -y && \
    yum install -y nvme-cli lvm2 util-linux && \
    yum clean all


# Copy the script into the container
RUN mkdir /pure-tools
COPY *.sh /pure-tools/
WORKDIR "/pure-tools"

# Set the entrypoint
ENTRYPOINT ["/pure-tools/rh_storage_collect.sh"]