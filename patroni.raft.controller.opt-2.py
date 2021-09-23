#!/usr/bin/env -S python -O -OO -b -B -q -x -X utf8 -W"ignore"

import logging
import os
import sys
from ipaddress import IPv4Address
from socket import getfqdn, gethostbyname
from typing import Dict, List, Union

import loguru
import prettytable
from patroni.raft_controller import main
from pydantic import BaseModel, BaseSettings, conint, constr, Field, root_validator, validator
from yarl import URL

if not __debug__: sys.tracebacklimit = 0


class Host(BaseModel):
    name: constr(regex=r'^[a-z0-9]+$')
    ip: IPv4Address
    port: conint(gt=1024, lt=65535)

    @property
    def env(self):
        return f'{self.ip}:{self.port}'

    def __str__(self):
        return self.env

    def __repr__(self):
        return self.env


class HostsSettings(BaseSettings):
    myself: Host = Field(default=..., env=r'PATRONI_RAFT_SELF_ADDR')
    partners: List[Host] = Field(default=..., env=r'PATRONI_RAFT_PARTNER_ADDRS')

    class Config:

        @staticmethod
        def json_loads(value: str) -> Union[Host, List[Host]]:
            urls: List[URL] = [URL(r'raft://' + i.strip(r"'")) for i in value.split(sep=r"','")]
            hosts: List[Host] = [
                    Host(name=getfqdn(name=i.host), ip=IPv4Address(address=gethostbyname(i.host)), port=i.port)
                    for i in urls]
            if hosts.__len__() == 1:
                return hosts[0]
            elif hosts.__len__() > 1:
                return hosts
            else:
                raise EnvironmentError

    @root_validator
    def root_validator(cls, values: Dict[str, Union[Host, List[Host]]]):  # noqa
        assert values.get(r'partners'), r'Пустой список партнеров'
        values.update(
                partners=[i for i in values.get(r'partners') if
                          not i == values.get(r'myself')])
        return values

    @property
    def getTable(self) -> prettytable.PrettyTable:
        return prettytable.PrettyTable(border=True, field_names=(r'Hostname', r'Address', r'Port'))

    @validator(r'myself', pre=False, each_item=False, always=True, check_fields=True, allow_reuse=True)
    def validator_myself(cls, value, values, config, field):  # noqa
        return value

    @validator(r'partners', pre=False, each_item=False, always=True, check_fields=True, allow_reuse=True)
    def validator_partners(cls, value, values, config, field):  # noqa
        return value


class InterceptHandler(logging.Handler):

    def emit(self, record):
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        loguru.logger.opt(depth=depth,
                          exception=record.exc_info).log(logging.getLevelName(record.levelno) or record.levelname,
                                                         record.getMessage())


def customize_logging(level: int):
    loguru.logger.remove()
    loguru.logger.opt(lazy=True, colors=True)
    loguru.logger.add(sink=sys.stdout, enqueue=True, diagnose=True, colorize=True,
                      serialize=False, catch=True, backtrace=True,
                      level=logging.getLevelName(level), format=r'<level>{level:<8}</level> '
                                                                r'<level>{thread.name}<yellow>@</yellow>{process.name}<yellow>#</yellow>'
                                                                r'{process.id}<yellow>@</yellow>{file}<yellow>#</yellow>{line}</level> '
                                                                r'| <cyan>{function}<yellow>@</yellow>{name}</cyan> '
                                                                r'| <level>{message}</level>')

    logging.basicConfig(handlers=[InterceptHandler()], level=level, force=True)

    _loggers = [_logger for _logger in logging.root.manager.loggerDict.values()
                if isinstance(_logger, logging.Logger)]
    for _logger in _loggers:
        _logger.handlers = []
        _logger.filters = []
        _logger.propagate = True
        _logger.disabled = False
        _logger.setLevel(logging.root.level)
    return loguru.logger


if __name__ == r'__main__':
    hosts = HostsSettings()

    tb = hosts.getTable

    tb.title = r'Собственный адрес в кластере'
    tb.add_row(tuple(hosts.myself.dict().values()))
    loguru.logger.debug(os.linesep + tb.get_string())

    tb.title = r'Ноды кластрера'
    tb.clear_rows()
    for partner in hosts.partners:
        tb.add_row(tuple(partner.dict().values()))
    loguru.logger.debug(os.linesep + tb.get_string())

    customize_logging(level=logging.DEBUG)

    loguru.logger.info(r'Стартуем')
    os.environ[r'PATRONI_RAFT_PARTNER_ADDRS'] = r",".join([f"'{i.env}'" for i in hosts.partners])
    os.environ[r'PATRONI_RAFT_SELF_ADDR'] = hosts.myself.env

    tb.clear()
    tb.title = r'Переменные окружения'
    tb.field_names = (r'Наименование', r'Значение')
    tb.add_rows(((HostsSettings.schema().get(r'properties').get(v).get(r'env'),
                  os.environ[HostsSettings.schema().get(r'properties').get(v).get(r'env')])
                 for v in HostsSettings.schema().get(r'properties')))
    loguru.logger.debug(os.linesep + tb.get_string())

    main()
    loguru.logger.info(r'Уходим')
