FROM albus/baseimage:master
RUN install_clean python3.9-full python3-pip \
 && update-alternatives --install /usr/local/bin/python python /usr/bin/python3.9 1 \
 && python -W"ignore" -m pip --no-cache-dir --no-python-version-warning \
    install --upgrade --prefer-binary pip ipaddress yarl pydantic patroni[raft] psycopg2-binary pipupgrade loguru \
 && python -W"ignore" -m pipupgrade --yes --latest --format=table --all
COPY --chown=root:root --chmod=0555 ./patroni.raft.controller.opt-2.py /usr/local/bin/
COPY --chown=root:root --chmod=0700 ./run /etc/service/raft/
ENV PATRONI_RAFT_SELF_ADDR="127.0.0.1:2222" PATRONI_RAFT_PARTNER_ADDRS="'127.0.0.2:2222'"
