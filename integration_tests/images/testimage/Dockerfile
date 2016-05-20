FROM debian:8

RUN apt-get update && apt-get upgrade -y
RUN apt-get install -y sysvinit-core
RUN apt-get remove -y systemd

# SSH
RUN apt-get install -y openssh-server
# configure SSH server
RUN mkdir /var/run/sshd
RUN mkdir -p /root/.ssh
# SSH login fix. Otherwise user is kicked off after login
RUN sed 's@session\s*required\s*pam_loginuid.so@session optional pam_loginuid.so@g' -i /etc/pam.d/sshd
COPY keys/unsecure_key.pub /root/.ssh/authorized_keys
RUN chmod 644 /root/.ssh/authorized_keys

CMD ["/usr/sbin/sshd", "-D"]
