#! /usr/bin/env python3
"""This script creates a fairly simple "skinny" cruise definition
file from a port_def.yaml specification that, in addition to other
destinations, also writes parsed data to InfluxDB. A typical
invocation would be

  local/usap/create_cruise.py \
    test/NBP1406/NBP1406_port_defs.yaml > test/NBP1406/NBP1406_cruise.yaml

It creates four modes:
  off      - nothing running
  port     - like no_write (below), but only run subset of loggers
  no_write - run all loggers, but don't write to disk
  write    - as above, but also write raw to file

All modes (except 'off') also write to InfluxDB and the cached data server.

Two derived data loggers are also included: true_wind and snapshot; these
are written to InfluxDB and the cached data server , but not disk.

There is no timeout checking of any loggers.
"""
import argparse
import getpass
import logging
import sys
import time
import yaml

from collections import OrderedDict

headers = """###########################################################
###########################################################
# YAML cruise definition file for OpenRVDAS.
#
# Created by:
#   command:  <<command_line>>
#   time:     <<date_time>> UTC
#   user:     <<user>>
#
###########################################################
cruise:
  id: <<cruise>>
  start: '<<cruise_start>>'
  end: '<<cruise_end>>'

###########################################################
includes:
  - local/logger_templates/serial_logger_template.yaml
  - local/logger_templates/udp_logger_template.yaml
  - local/logger_templates/parse_data_logger_template.yaml
  - local/logger_templates/true_winds_logger_template.yaml
  - local/logger_templates/snapshot_logger_template.yaml
"""

################################################################################
def create_variables_section(port_def):
  variables_section = f"""
###########################################################
# Global variables - can be overridden by individual loggers
variables:
  cruise: {port_def.get('cruise', {}).get('id')}
  cruise_start: '{port_def.get('cruise', {}).get('start')}'
  cruise_end: '{port_def.get('cruise', {}).get('end')}'
  
  udp_destination: {port_def.get('network', {}).get('destination', '255.255.255.255')}
  raw_udp_port: {port_def.get('network', {}).get('raw_udp_port')}
  parsed_udp_port: {port_def.get('network', {}).get('parsed_udp_port')}
  
  file_root: {port_def.get('file_root', '/var/tmp/log')}
  parse_definition_path: {port_def.get('parse_definition_path', '')}

  data_server: {port_def.get('network', {}).get('data_server')}
  influx_bucket_name: openrvdas
  
  command_line: {' '.join(sys.argv)}
  date_time: {time.asctime(time.gmtime())}
  user: {getpass.getuser()}
"""
  return variables_section

################################################################################
def create_loggers_section(port_def):
  loggers = port_def.get('ports').keys()
  loggers_section = f"""
###########################################################
loggers:
"""
  for logger in loggers:
    logger_port_def = port_def.get('ports').get(logger).get('port_tab')
    if not logger_port_def:
      logging.warning('No port def for %s', logger)

    (inst, tty, baud, datab, stopb, parity, igncr, icrnl, eol, onlcr,
     ocrnl, icanon, vmin, vtime, vintr, vquit, opost) = logger_port_def.split()

    loggers_section += f"""  {logger}:
    logger_template: serial_logger_template
    variables:
      serial_port: {tty}
      baud_rate: {baud}
"""
  loggers_section += """
  # Parse raw UDP data and send to CDS, and optionally InfluxDB;
  # uses default global variables
  parse_data:
    logger_template: parse_data_logger_template
    
  # Read course, heading, SOG and relative winds from CDS, compute
  # true winds and write back to CDS and optionally InfluxDB
  true_winds:
    logger_template: true_winds_logger_template

  # Read a bunch of variables from CDS, compute 30-second snapshot and write back
  # to CDS and optionally InfluxDB. This *totally* needs a way to be generalized!!!
  snapshot:
    logger_template: snapshot_logger_template
    variables:
      interval: 30
      window: 30
"""
  return loggers_section

################################################################################
def create_modes_section(port_def):
  loggers = port_def.get('ports').keys()
  modes_section = f"""
###########################################################
modes:
  'off':
"""
  for logger in loggers:
    modes_section += f'    {logger}: {logger}-off\n'
  modes_section += '    parse_data: parse_data-off\n'
  modes_section += '    true_winds: true_winds-off\n'
  modes_section += '    snapshot: snapshot-off\n'

  #### no_write
  modes_section += """
  no_write:
"""
  for logger in loggers:
    modes_section += f'    {logger}: {logger}-net\n'
  modes_section += '    parse_data: parse_data-on\n'
  modes_section += '    true_winds: true_winds-on\n'
  modes_section += '    snapshot: snapshot-on\n'

  #### no_write+influx
  modes_section += """
  no_write+influx:
"""
  for logger in loggers:
    modes_section += f'    {logger}: {logger}-net\n'
  modes_section += '    parse_data: parse_data-on+influx\n'
  modes_section += '    true_winds: true_winds-on+influx\n'
  modes_section += '    snapshot: snapshot-on+influx\n'

  #### write
  modes_section += """
  write:
"""
  for logger in loggers:
    modes_section += f'    {logger}: {logger}-net+file\n'
  modes_section += '    parse_data: parse_data-on\n'
  modes_section += '    true_winds: true_winds-on\n'
  modes_section += '    snapshot: snapshot-on\n'

  #### write+influx
  modes_section += """
  write+influx:
"""
  for logger in loggers:
    modes_section += f'    {logger}: {logger}-net+file\n'
  modes_section += '    parse_data: parse_data-on+influx\n'
  modes_section += '    true_winds: true_winds-on+influx\n'
  modes_section += '    snapshot: snapshot-on+influx\n'

  modes_section += """
###########################################################
default_mode: 'off'
"""
  return modes_section

################################################################################
################################################################################
parser = argparse.ArgumentParser()
parser.add_argument('def_filename', metavar='def_filename', type=str,
                    help='YAML file containing cruise and port specifications')
args = parser.parse_args()

with open(args.def_filename, 'r') as fp:
  try:
    port_def = yaml.load(fp, Loader=yaml.FullLoader)
  except AttributeError:
    # If they've got an older yaml, it may not have FullLoader)
    port_def = yaml.load(fp)

output = headers
output += create_variables_section(port_def)
output += create_loggers_section(port_def)
output += create_modes_section(port_def)

print(output)
