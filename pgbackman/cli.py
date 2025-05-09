#!/usr/bin/env python2
#
# Copyright (c) 2013-2014 Rafael Martinez Guerrero / PostgreSQL-es
# rafael@postgresql.org.es / http://www.postgresql.org.es/
#
# Copyright (c) 2014 USIT-University of Oslo
#
# Copyright (c) 2023 James Miller
#
# This file is part of PgBackMan
# https://github.com/jvaskonen/pgbackman
#
# PgBackMan is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# PgBackMan is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PgBackMan.  If not, see <http://www.gnu.org/licenses/>.
#

import cmd
import sys
import os
import time
import signal
import shlex
import datetime
import subprocess
import re
import readline
import socket
import json
import hashlib
import random

from pgbackman.database import *
from pgbackman.config import *
from pgbackman.logs import *
from pgbackman.prettytable import *
from pgbackman.ordereddict import OrderedDict

import pgbackman.version


# ############################################
# class PgbackmanCli
# ############################################


class PgbackmanCli(cmd.Cmd):
    """
    This class implements the pgbackman shell. It is based on the python module cmd
    """

    # ###############################
    # Constructor
    # ###############################

    def __init__(self):
        cmd.Cmd.__init__(self)

        try:
            self.software_version_tag = self.get_pgbackman_software_version_tag()
            self.software_version_number = self.get_pgbackman_software_version_number()

        except Exception as e:
            print '''
            ERROR: Problems getting the version tag and number of this PgBackman installation.
            The execution is aborted to avoid problems in case there is a mismatch between the version
            of the software and the version of the database.
            '''

            sys.exit(1)

        self.intro =  '\n####################################################################\n' + \
            'Welcome to the PostgreSQL Backup Manager shell ver.' + self.software_version_tag + '\n' + \
            '####################################################################\n' + \
            'Type help or \? to list commands.\n'

        self.prompt = '[pgbackman]$ '
        self.file = None

        self.conf = PgbackmanConfiguration()
        self.dsn = self.conf.dsn

        self.logs = PgbackmanLogs('pgbackman_cli', '', '')

        self.db = PgbackmanDB(self.dsn, 'pgbackman_cli')
        self.output_format = 'table'

        self.backup_server_id = ''

        self.execution_modus = 'interactive'


    # ############################################
    # Method do_show_backup_servers
    # ############################################

    def do_show_backup_servers(self,args):
        '''
        DESCRIPTION:
        This command shows all backup servers registered in PgBackMan.

        COMMAND:
        show_backup_servers

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        if len(arg_list) == 0:
            try:
                result = self.db.show_backup_servers()

                colnames = [desc[0] for desc in result.description]
                self.generate_output(result,colnames,["FQDN","Remarks"],'backup_servers')

            except Exception as e:
                print '--------------------------------------------------------'
                self.processing_error('[ERROR]: ' + str(e) + '\n')

        else:
            self.processing_error('\n[ERROR] - This command does not accept parameters.\n          Type help or \? to list commands\n')

        print


    # ############################################
    # Method do_register_backup_server
    # ############################################

    def do_register_backup_server(self,args):
        '''
        DESCRIPTION:
        This command registers a backup server in PgBackMan.

        COMMAND:
        register_backup_server [hostname]
                               [domain]
                               [remarks]

        [hostname]:
        -----------
        Hostname of the backup server.

        [domain]:
        ---------
        Domain name of the backup server

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        try:
            domain_default = self.db.get_default_backup_server_parameter('domain')
            status_default = self.db.get_default_backup_server_parameter('backup_server_status')

        except Exception as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: Problems getting default values for parameters\n' + str(e) + '\n')
            return False

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            ack = ''

            try:
                print '--------------------------------------------------------'
                hostname = raw_input('# Hostname []: ')
                domain = raw_input('# Domain [' + domain_default + ']: ')
                remarks = raw_input('# Remarks []: ')
                print

                while ack != 'yes' and ack != 'no':
                    ack = raw_input('# Are all values correct (yes/no): ')

                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            if domain == '':
                domain = domain_default

            if ack.lower() == 'yes':
                try:
                    self.db.register_backup_server(hostname.lower().strip(),domain.lower().strip(),status_default.upper().strip(),remarks.strip())
                    print '[DONE] Backup server ' + hostname.lower().strip() + '.' + domain.lower().strip() + ' registered.\n'

                except Exception as e:
                    self.processing_error('[ERROR]: Could not register this backup server\n' + str(e) + '\n')

            elif ack.lower() == 'no':
                print '[ABORTED] Command interrupted by the user.\n'

        #
        # Command with parameters
        #

        elif len(arg_list) == 3:

            hostname = arg_list[0]
            domain = arg_list[1]
            remarks = arg_list[2]

            if domain == '':
                domain = domain_default

            try:
                status_default = self.db.get_default_backup_server_parameter('backup_server_status')

                self.db.register_backup_server(hostname.lower().strip(),domain.lower().strip(),status_default.upper().strip(),remarks.strip())
                print '[DONE] Backup server ' + hostname.lower().strip() + '.' + domain.lower().strip() + ' registered.\n'

            except Exception as e:
                self.processing_error('[ERROR]: Could not register this backup server\n' + str(e) + '\n')

        #
        # Command with the wrong number of parameters
        #

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or \? to list commands\n')

        print


    # ############################################
    # Method do_delete_backup_server
    # ############################################

    def do_delete_backup_server(self,args):
        '''
        DESCRIPTION:
        This command deletes a backup server registered in PgBackMan.

        NOTE: This command will not work if there are backup definitions
        registered in the server we want to delete. This is done on purpose
        to avoid operator errors with catastrophic consequences.

        One will have to delete or move to another server all backup definitions
        running on the server that you want to delete.

        COMMAND:
        delete_backup_server [SrvID | FQDN]

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Default backup server
        #

        default_backup_server = self.get_default_backup_server()

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            ack = ''

            try:
                print '--------------------------------------------------------'
                server_id = raw_input('# SrvID / FQDN [' + default_backup_server + ']: ')
                print

                while ack != 'yes' and ack != 'no':
                    ack = raw_input('# Are you sure you want to delete this server? (yes/no): ')

                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            if server_id == '':
                server_id = default_backup_server

            if ack.lower() == 'yes':

                try:
                    if server_id.isdigit():
                        self.db.delete_backup_server(server_id)
                        print '[DONE] Backup server deleted.\n'

                    else:
                        self.db.delete_backup_server(self.db.get_backup_server_id(server_id))
                        print '[DONE] Backup server deleted.\n'

                except Exception as e:
                    self.processing_error('[ERROR]: Could not delete this backup server\n' + str(e) + '\n')

            elif ack.lower() == 'no':
                print '[ABORTED] Command interrupted by the user.\n'

        #
        # Command with parameters
        #

        elif len(arg_list) == 1:

            server_id = arg_list[0]

            if server_id == '':
                server_id = default_backup_server

            try:
                if server_id.isdigit():
                    self.db.delete_backup_server(server_id)
                    print '[DONE] backup server deleted.\n'

                else:
                    self.db.delete_backup_server(self.db.get_backup_server_id(server_id))
                    print '[DONE] Backup server deleted.\n'

            except Exception as e:
                self.processing_error('[ERROR]: Could not delete this backup server\n' + str(e) + '\n')

        #
        # Command with the wrong number of parameters
        #

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or \? to list commands\n')

        print


    # ############################################
    # Method do_show_pgsql_nodes
    # ############################################

    def do_show_pgsql_nodes(self,args):
        '''
        DESCRIPTION:
        This command shows all PgSQL nodes registered in PgBackMan.

        COMMAND:
        show_pgsql_nodes

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        if len(arg_list) == 0:
            try:
                result = self.db.show_pgsql_nodes()

                colnames = [desc[0] for desc in result.description]
                self.generate_output(result,colnames,["FQDN","Remarks"],'pgsql_nodes')

            except Exception as e:
                print '--------------------------------------------------------'
                self.processing_error('[ERROR]: ' + str(e) + '\n')

        else:
            self.processing_error('\n[ERROR] - This command does not accept parameters.\n          Type help or ? to list commands\n')

        print


    # ############################################
    # Method do_register_pgsql_node
    # ############################################

    def do_register_pgsql_node(self,args):
        '''
        DESCRIPTION:
        This command registers a PgSQL node in PgBackMan.

        COMMAND:
        register_pgsql_node [hostname]
                            [domain]
                            [pgport]
                            [admin_user]
                            [status]
                            [remarks]

        [hostname]:
        -----------
        Hostname of the PgSQL node.

        [domain]:
        ---------
        Domain name of the PgSQL node.

        [pgport]:
        ---------
        PostgreSQL port.

        [admin_user]:
        -------------
        PostgreSQL admin user.

        [Status]:
        ---------
        RUNNING: PostgreSQL node running and online
        DOWN: PostgreSQL node not online.

        [remarks]:
        ----------
        Remarks

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        try:
            domain_default = self.db.get_default_pgsql_node_parameter('domain')
            port_default = self.db.get_default_pgsql_node_parameter('pgport')
            admin_user_default = self.db.get_default_pgsql_node_parameter('admin_user')
            status_default = self.db.get_default_pgsql_node_parameter('pgsql_node_status')

        except Exception as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: Problems getting default values for parameters\n' + str(e) + '\n')
            return False

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            ack = ''

            try:
                print '--------------------------------------------------------'
                hostname = raw_input('# Hostname []: ')
                domain = raw_input('# Domain [' + domain_default + ']: ')
                port = raw_input('# Port [' + port_default + ']: ')
                admin_user = raw_input('# Admin user [' + admin_user_default + ']: ')
                status = raw_input('# Status[' + status_default + ']: ')
                remarks = raw_input('# Remarks []: ')
                print

                while ack != 'yes' and ack != 'no':
                    ack = raw_input('# Are all values correct (yes/no): ')

                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            if domain == '':
                domain = domain_default

            if port == '':
                port = port_default

            if admin_user == '':
                admin_user = admin_user_default

            if status == '':
                status = status_default

            if ack.lower() == 'yes':
                if self.check_port(port):
                    try:
                        self.db.register_pgsql_node(hostname.lower().strip(),domain.lower().strip(),port.strip(),admin_user.lower().strip(),status.upper().strip(),remarks.strip())
                        print '[DONE] PgSQL node ' + hostname.lower().strip() + '.' + domain.lower().strip() + ' registered.\n'

                    except Exception as e:
                        self.processing_error('[ERROR]: Could not register this PgSQL node\n' + str(e) + '\n')

            elif ack.lower() == 'no':
                print '[ABORTED] Command interrupted by the user.\n'

        #
        # Command with parameters
        #

        elif len(arg_list) == 6:

            hostname = arg_list[0]
            domain = arg_list[1]
            port = arg_list[2]
            admin_user = arg_list[3]
            status = arg_list[4]
            remarks = arg_list[5]

            if domain == '':
                domain = domain_default

            if port == '':
                port = port_default

            if admin_user == '':
                admin_user = admin_user_default

            if status == '':
                status = status_default

            if self.check_port(port):
                try:
                    self.db.register_pgsql_node(hostname.lower().strip(),domain.lower().strip(),port.strip(),admin_user.lower().strip(),status.upper().strip(),remarks.strip())
                    print '[DONE] PgSQL node ' + hostname.lower().strip() + '.' + domain.lower().strip() + ' registered.\n'

                except Exception as e:
                    self.processing_error('[ERROR]: Could not register this PgSQL node\n' + str(e) + '\n')

        #
        # Command with the wrong number of parameters
        #

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or \? to list commands\n')

        print


    # ############################################
    # Method do_delete_pgsql_node
    # ############################################

    def do_delete_pgsql_node(self,args):
        '''
        DESCRIPTION:
        This command deletes a PgSQL node registered in PgBackMan.

        NOTE: This command will not work if there are backup job definitions
        registered in the server we want to delete. This is done on purpose
        to avoid operator errors with catastrophic consequences.

        You will have to delete all backup definitions for the server that
        you want to delete.

        COMMAND:
        delete_pgsql_node [NodeID | FQDN]

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            ack = ''

            try:
                print '--------------------------------------------------------'
                node_id = raw_input('# NodeID / FQDN: ')
                print

                while ack != 'yes' and ack != 'no':
                    ack = raw_input('# Are you sure you want to delete this server? (yes/no): ')

                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            if ack.lower() == 'yes':

                try:
                    if node_id.isdigit():
                        self.db.delete_pgsql_node(node_id)
                        print '[DONE] PgSQL node deleted.\n'

                    else:
                        self.db.delete_pgsql_node(self.db.get_pgsql_node_id(node_id))
                        print '[DONE] PgSQL node deleted.\n'

                except Exception as e:
                    self.processing_error('[ERROR]: Could not delete this PgSQL node\n' + str(e) + '\n')

            elif ack.lower() == 'no':
                print '[ABORTED] Command interrupted by the user.\n'

        #
        # Command with parameters
        #

        elif len(arg_list) == 1:

            node_id = arg_list[0]

            try:
                if node_id.isdigit():
                    self.db.delete_pgsql_node(node_id)
                    print '[DONE] PgSQL node deleted.\n'

                else:
                    self.db.delete_pgsql_node(self.db.get_pgsql_node_id(node_id))
                    print '[DONE] PgSQL node deleted.\n'

            except Exception as e:
                self.processing_error('[ERROR]: Could not delete this PgSQL node\n' + str(e) + '\n')

        #
        # Command with the wrong number of parameters
        #

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or \? to list commands\n')

        print


    # ############################################
    # Method do_show_backup_definitions
    # ############################################

    def do_show_backup_definitions(self,args):
        '''DESCRIPTION:
        This command shows all backup definitions
        for a particular combination of parameter values.

        COMMAND:
        show_backup_definitions [SrvID|FQDN]
                                [NodeID|FQDN]
                                [DBname]

        [SrvID|FQDN]:
        -------------
        SrvID in PgBackMan or FQDN of the backup server. One can use
        'all' or '*' with this parameter.

        [NodeID|FQDN]:
        --------------
        NodeID in PgBackMan or FQDN of the PgSQL node. One can use
        'all' or '*' with this parameter.

        [DBname]:
        ---------
        Database name. One can use 'all' or '*' with this parameter.

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False


        #
        # Default backup server
        #

        default_backup_server = self.get_default_backup_server()

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            try:
                print '--------------------------------------------------------'
                server_id = raw_input('# SrvID / FQDN [' + default_backup_server + ']: ')
                node_id = raw_input('# NodeID / FQDN [all]: ')
                dbname = raw_input('# DBname [all]: ')
                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            if server_id == '':
                server_id = default_backup_server

            if server_id.lower() in ['all','*']:
                server_list = None
            else:
                server_list = server_id.strip().replace(' ','').split(',')

            if node_id.lower() in ['all','*','']:
                node_list = None
            else:
                node_list = node_id.strip().replace(' ','').split(',')

            if dbname.lower() in ['all','*','']:
                dbname_list = None
            else:
                dbname_list = dbname.strip().replace(' ','').split(',')

            try:
                result = self.db.show_backup_definitions(server_list,node_list,dbname_list)

                colnames = [desc[0] for desc in result.description]
                self.generate_output(result,colnames,["Backup server","PgSQL node","DBname","Schedule","Code","Parameters"],'backup_definitions')

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')

        #
        # Command with parameters
        #

        elif len(arg_list) == 3:

            server_id = arg_list[0]
            node_id = arg_list[1]
            dbname = arg_list[2]

            if server_id == '':
                server_id = default_backup_server

            if server_id.lower() in ['all','*']:
                server_list = None
            else:
                server_list = server_id.strip().replace(' ','').split(',')

            if node_id.lower() in ['all','*','']:
                node_list = None
            else:
                node_list = node_id.strip().replace(' ','').split(',')

            if dbname.lower() in ['all','*','']:
                dbname_list = None
            else:
                dbname_list = dbname.strip().replace(' ','').split(',')

            if self.output_format == 'table':

                print '--------------------------------------------------------'
                print '# SrvID / FQDN: ' + server_id
                print '# NodeID / FQDN: ' + node_id
                print '# DBname: ' + dbname
                print '--------------------------------------------------------'

            try:
                result = self.db.show_backup_definitions(server_list,node_list,dbname_list)

                colnames = [desc[0] for desc in result.description]
                self.generate_output(result,colnames,["Backup server","PgSQL node","DBname","Schedule","Code","Parameters"],'backup_definitions')

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')

        #
        # Command with the wrong number of parameters
        #

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        print


    # ############################################
    # Method do_register_backup_definition
    # ############################################

    def do_register_backup_definition(self,args):
        '''DESCRIPTION:
        This command registers a backup definition that
        will be run periodically by PgBackMan.

        COMMAND:
        register_backup_definition [SrvID | FQDN]
                                   [NodeID | FQDN]
                                   [DBname]
                                   [DBname exceptions]
                                   [min_cron]
                                   [hour_cron]
                                   [day-month_cron]
                                   [month_cron]
                                   [weekday_cron]
                                   [backup code]
                                   [encryption]
                                   [retention period]
                                   [retention redundancy]
                                   [extra backup parameters]
                                   [job status]
                                   [remarks]

        [SrvID | FQDN]:
        ---------------
        SrvID in PgBackMan or FQDN of the backup server that will run
        the backup job.

        [NodeID | FQDN]:
        ----------------
        NodeID in PgBackMan or FQDN of the PgSQL node running the
        database to backup.

        [Dbname]:
        ---------
        Database name.

        One can use these two special values:

        * '#all_databases#' if you want to register the backup
        definition for *all databases* in the cluster (except
        'template0','template1' and 'postgres').

        * '#databases_without_backup_definitions#' if you want to register the backup
        definition for all databases in the cluster *without* a backup
        definition (except 'template0','template1' and 'postgres').

        [DBname exceptions]
        -------------------
        Databases that will not be considered when using the values
        '#all_databases#' or '#databases_without_backup_definitions#'
        in [DBname].

        One can define several DBnames in a comma separated list.

        [*cron]:
        --------
        Schedule definition using the cron expression. Check
        http://en.wikipedia.org/wiki/Cron#CRON_expression for more
        information.

        [backup code]:
        --------------
        CLUSTER: Backup of all databases in a PgSQL node
        FULL: Full Backup of a database. Schema + data + owner globals + DB globals.
        SCHEMA: Schema backup of a database. Schema + owner globals + DB globals.
        DATA: Data backup of the database.

        [encryption]:
        ------------
        TRUE: GnuPG encryption activated.
        FALSE: GnuPG encryption NOT activated.

        [retention period]:
        -------------------
        Time interval, e.g. 2 hours, 3 days, 1 week, 1 month, 2 years, ...

        [retention redundancy]:
        -----------------------
        Integer: 1,2,3, .... Minimun number of backups to keep in the catalog
        regardless of the retention period used.

        [extra backup parameters]:
        ---------------
        Extra parameters that can be used with pg_dump / pg_dumpall

        [job status]:
        -------------
        ACTIVE: Backup job activated and in production.
        STOPPED: Backup job stopped.

        '''

        database_list = []

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        minutes_cron_default = hours_cron_default = weekday_cron_default = month_cron_default = day_month_cron_default = \
            backup_code_default = encryption_default = retention_period_default = retention_redundancy_default = \
            extra_backup_parameters_default = backup_job_status_default = ''

        #
        # Default backup server
        #

        default_backup_server = self.get_default_backup_server()

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            ack = ''

            #
            # Getting the backup definition parameters
            #

            try:

                print '--------------------------------------------------------'
                backup_server = raw_input('# Backup server SrvID / FQDN [' + default_backup_server + ']: ').strip()
                pgsql_node = raw_input('# PgSQL node NodeID / FQDN []: ').strip()

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            try:

                if backup_server == '':
                    backup_server = default_backup_server

                if backup_server.isdigit():
                    backup_server_id = backup_server
                else:
                    backup_server_id = self.db.get_backup_server_id(backup_server)

                if pgsql_node.isdigit():
                    pgsql_node_id = pgsql_node
                    pgsql_node_fqdn = self.db.get_pgsql_node_fqdn(pgsql_node)
                else:
                    pgsql_node_id = self.db.get_pgsql_node_id(pgsql_node)
                    pgsql_node_fqdn = pgsql_node

            except Exception as e:
                print '--------------------------------------------------------'
                self.processing_error('[ERROR]: ' + str(e) + '\n')
                return False

            #
            # Getting some default values for the PgSQL node defined
            #

            try:
                minutes_cron_default = self.db.get_minute_from_interval(self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_minutes_interval'))
                hours_cron_default = self.db.get_hour_from_interval(self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_hours_interval'))
                weekday_cron_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_weekday_cron')
                month_cron_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_month_cron')
                day_month_cron_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_day_month_cron')
                backup_code_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_code')
                encryption_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'encryption')
                retention_period_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'retention_period')
                retention_redundancy_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'retention_redundancy')
                extra_backup_parameters_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'extra_backup_parameters')
                backup_job_status_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_job_status')

            except Exception as e:
                print '--------------------------------------------------------'
                self.processing_error('[ERROR]: Problems getting default values for parameters\n' + str(e) + '\n')
                return False

            try:
                dbname = raw_input('# DBname []: ')
                dbname_exceptions = raw_input('# DBname exceptions []: ')

                if dbname != '#all_databases#' and dbname != '#databases_without_backup_definitions#':
                    minutes_cron = raw_input('# Minutes cron [' + str(minutes_cron_default) + ']: ')
                    hours_cron = raw_input('# Hours cron [' + str(hours_cron_default) + ']: ')

                day_month_cron = raw_input('# Day-month cron [' + day_month_cron_default + ']: ')
                month_cron = raw_input('# Month cron [' + month_cron_default + ']: ')
                weekday_cron = raw_input('# Weekday cron [' + weekday_cron_default + ']: ')
                backup_code = raw_input('# Backup code [' + backup_code_default + ']: ')
                encryption = raw_input('# Encryption [' + encryption_default + ']: ')
                retention_period = raw_input('# Retention period [' + retention_period_default + ']: ')
                retention_redundancy = raw_input('# Retention redundancy [' + retention_redundancy_default + ']: ')
                extra_backup_parameters = raw_input('# Extra parameters [' + extra_backup_parameters_default + ']: ')
                backup_job_status = raw_input('# Job status [' + backup_job_status_default + ']: ')
                remarks = raw_input('# Remarks []: ')
                print

                while ack != 'yes' and ack != 'no':
                    ack = raw_input('# Are all values correct (yes/no): ')

                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            if ack.lower() == 'yes':

                try:
                    dsn_value = self.db.get_pgsql_node_dsn(pgsql_node_id)
                    db_node = PgbackmanDB(dsn_value, 'pgbackman_cli')

                    dbname_exceptions_list = dbname_exceptions.replace(' ','').split(',')

                    #
                    # Generating a list of databases that will get a backup definition
                    #

                    if dbname == '#all_databases#':

                        for database in db_node.get_pgsql_node_database_list():

                            if database[0] not in dbname_exceptions_list:
                                database_list.append(database[0])

                    elif dbname == '#databases_without_backup_definitions#':

                        #
                        # We need to define an empty database in these
                        # two list because backup definitions of type
                        # CLUSTER has a dbname value = ''
                        #

                        all_databases = ['']
                        databases_with_bckdef = ['']

                        for database in db_node.get_pgsql_node_database_list():

                            if database[0] not in dbname_exceptions_list:
                                all_databases.append(database[0])

                        for database in self.db.get_pgsql_node_database_with_bckdef_list(pgsql_node_id):

                            if database[0] not in dbname_exceptions_list:
                                databases_with_bckdef.append(database[0])

                        database_list = set(all_databases) - set(databases_with_bckdef)

                    else:
                        database_list = dbname.strip().replace(' ','').split(',')

                except Exception as e:
                    self.processing_error('[ERROR]: ' + str(e) + '\n')
                    return False

                #
                # Loop through the list of databases that will get a backup definition
                #

                for index,database in enumerate(database_list):

                    error = False

                    #
                    # Check if the database exists in the PgSQL node
                    #

                    if database != '' and database != '#all_databases#' and database != '#databases_without_backup_definitions#':

                        try:
                            if not db_node.database_exists(database):
                                self.processing_error('[ERROR]: Database [' + database + '] does not exist in The PgSQL node [' + pgsql_node_fqdn + ']')

                                error = True

                        except Exception as e:
                            self.processing_error('[ERROR]: ' + str(e) + '\n')

                            error = True


                    #
                    # If we have defined more than one database, generate a random value for cron minutes and cron hours.
                    #

                    if dbname == '#all_databases#' or dbname == '#databases_without_backup_definitions#' or len(database_list) > 1:

                        try:
                            minutes_cron = self.db.get_minute_from_interval(self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_minutes_interval'))
                            hours_cron = self.db.get_hour_from_interval(self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_hours_interval'))

                        except Exception as e:
                            print '--------------------------------------------------------'
                            self.processing_error('[ERROR]: Problems getting default values for parameters\n' + str(e) + '\n')

                            error = True

                    else:
                        if minutes_cron == '':
                            minutes_cron = str(minutes_cron_default)

                        if hours_cron == '':
                            hours_cron = str(hours_cron_default)

                    if weekday_cron == '':
                        weekday_cron = weekday_cron_default

                    if month_cron == '':
                        month_cron = month_cron_default

                    if day_month_cron == '':
                        day_month_cron = day_month_cron_default

                    if backup_code == '':
                        backup_code = backup_code_default

                    if encryption == '':
                        encryption = encryption_default

                    if retention_period == '':
                        retention_period = retention_period_default

                    if retention_redundancy == '':
                        retention_redundancy = retention_redundancy_default

                    if extra_backup_parameters == '':
                        extra_backup_parameters = extra_backup_parameters_default

                    if backup_job_status == '':
                        backup_job_status = backup_job_status_default

                    try:
                        if error == False:

                            self.db.register_backup_definition(backup_server_id,pgsql_node_id,database.strip(),minutes_cron,hours_cron,day_month_cron.strip(), \
                                                                   month_cron.strip(),weekday_cron.strip(),backup_code.upper().strip(),encryption.lower().strip(), \
                                                                   retention_period.lower().strip(),retention_redundancy.strip(),extra_backup_parameters.lower().strip(), \
                                                                   backup_job_status.upper().strip(),remarks.strip())

                            print '[DONE] Backup definition for dbname: [' + database.strip() + '] registered.\n'

                    except Exception as e:
                        self.processing_error('[ERROR]: Could not register this backup definition\n' + str(e) + '\n')

            elif ack.lower() == 'no':

                print '[ABORTED] Command interrupted by the user.\n'

            db_node = None

        #
        # Command with parameters
        #

        elif len(arg_list) == 16:

            backup_server = arg_list[0]
            pgsql_node = arg_list[1]

            try:

                if backup_server == '':
                    backup_server = default_backup_server

                if backup_server.isdigit():
                    backup_server_id = backup_server
                else:
                    backup_server_id = self.db.get_backup_server_id(backup_server)

                if pgsql_node.isdigit():
                    pgsql_node_id = pgsql_node
                    pgsql_node_fqdn = self.db.get_pgsql_node_fqdn(pgsql_node)
                else:
                    pgsql_node_id = self.db.get_pgsql_node_id(pgsql_node)
                    pgsql_node_fqdn = pgsql_node

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')
                return False

            #
            # Getting some default values
            #

            try:
                minutes_cron_default = self.db.get_minute_from_interval(self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_minutes_interval'))
                hours_cron_default = self.db.get_hour_from_interval(self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_hours_interval'))
                weekday_cron_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_weekday_cron')
                month_cron_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_month_cron')
                day_month_cron_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_day_month_cron')
                backup_code_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_code')
                encryption_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'encryption')
                retention_period_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'retention_period')
                retention_redundancy_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'retention_redundancy')
                extra_backup_parameters_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'extra_backup_parameters')
                backup_job_status_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_job_status')

            except Exception as e:
                print '--------------------------------------------------------'
                self.processing_error('[ERROR]: Problems getting default values for parameters\n' + str(e) + '\n')
                return False

            dbname = arg_list[2]
            dbname_exceptions = arg_list[3]
            minutes_cron = arg_list[4]
            hours_cron = arg_list[5]
            day_month_cron = arg_list[6]
            month_cron = arg_list[7]
            weekday_cron = arg_list[8]
            backup_code = arg_list[9]
            encryption = arg_list[10]
            retention_period = arg_list[11]
            retention_redundancy = arg_list[12]
            extra_backup_parameters = arg_list[13]
            backup_job_status = arg_list[14]
            remarks = arg_list[15]

            try:
                dsn_value = self.db.get_pgsql_node_dsn(pgsql_node_id)
                db_node = PgbackmanDB(dsn_value, 'pgbackman_cli')

                dbname_exceptions_list = dbname_exceptions.replace(' ','').split(',')

                if dbname == '#all_databases#':

                    for database in db_node.get_pgsql_node_database_list():

                        if database[0] not in dbname_exceptions_list:
                            database_list.append(database[0])

                elif dbname == '#databases_without_backups#':

                    all_databases = []
                    databases_with_bckdef = []

                    for database in db_node.get_pgsql_node_database_list():

                        if database[0] not in dbname_exceptions_list:
                            all_databases.append(database[0])

                    for database in self.db.get_pgsql_node_database_with_bckdef_list(pgsql_node_id):

                        if database[0] not in dbname_exceptions_list:
                            databases_with_bckdef.append(database[0])

                    database_list = set(all_databases) - set(databases_with_bckdef)

                else:
                    database_list = dbname.strip().replace(' ','').split(',')

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')
                return False

            for index,database in enumerate(database_list):

                error = False

                if database != '':

                    try:
                        if not db_node.database_exists(database):
                            self.processing_error('[ERROR]: Database [' + database + '] does not exist in The PgSQL node [' + pgsql_node_fqdn + ']')

                            error = True

                            if index == len(database_list) - 1:
                                db_node = None
                                return False

                    except Exception as e:
                        self.processing_error('[ERROR]: ' + str(e) + '\n')

                        error = true

                        if index == len(database_list) - 1:
                            return False

                if dbname == '#all_databases#' or dbname == '#databases_without_backups#' or len(database_list) > 1:

                    try:
                        minutes_cron = self.db.get_minute_from_interval(self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_minutes_interval'))
                        hours_cron = self.db.get_hour_from_interval(self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_hours_interval'))

                    except Exception as e:
                        print '--------------------------------------------------------'
                        self.processing_error('[ERROR]: Problems getting default values for parameters\n' + str(e) + '\n')

                        error = True

                        if index == len(database_list) - 1:
                            return False

                else:
                    if minutes_cron == '':
                        minutes_cron = str(minutes_cron_default)

                    if hours_cron == '':
                        hours_cron = str(hours_cron_default)

                if weekday_cron == '':
                    weekday_cron = weekday_cron_default

                if month_cron == '':
                    month_cron = month_cron_default

                if day_month_cron == '':
                    day_month_cron = day_month_cron_default

                if backup_code == '':
                    backup_code = backup_code_default

                if encryption == '':
                    encryption = encryption_default

                if retention_period == '':
                    retention_period = retention_period_default

                if retention_redundancy == '':
                    retention_redundancy = retention_redundancy_default

                if extra_backup_parameters == '':
                    extra_backup_parameters = extra_backup_parameters_default

                if backup_job_status == '':
                    backup_job_status = backup_job_status_default

                try:
                    if error == False:
                        self.db.register_backup_definition(backup_server_id,pgsql_node_id,database.strip(),minutes_cron,hours_cron,day_month_cron.strip(), \
                                                                   month_cron.strip(),weekday_cron.strip(),backup_code.upper().strip(),encryption.lower().strip(), \
                                                                   retention_period.lower().strip(),retention_redundancy.strip(),extra_backup_parameters.lower().strip(), \
                                                                   backup_job_status.upper().strip(),remarks.strip())

                        print '[DONE] Backup definition for dbname: [' + database.strip() + '] Registered.\n'

                except Exception as e:
                    self.processing_error('[ERROR]: Could not register this backup definition\n' + str(e) + '\n')

            db_node = None

        #
        # Command with the wrong number of parameters
        #

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or \? to list commands\n')

        print


    # ############################################
    # Method do_delete_backup_definition_id
    # ############################################

    def do_delete_backup_definition_id(self,args):
        '''
        DESCRIPTION:
        This command deletes a backup definition for a DefID.

        NOTE: You have to use the parameter force-deletion
        if you want to force the deletion of backup definitions
        with active backups in the catalog

        If you use force-deletion, all backups in the catalog for
        the backup definition deleted, will be deleted regardless of
        the retention period or retention redundancy used.

        *** Use with precaution ***

        COMMAND:
        delete_backup_definition_id [DefID]
                                    [force-deletion]

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            ack = ''
            force_deletion = ''

            try:
                print '--------------------------------------------------------'
                def_id = raw_input('# DefID: ')

                while force_deletion != 'y' and force_deletion != 'n':
                    force_deletion = raw_input('# Force deletion (y/n): ')

                print

                while ack != 'yes' and ack != 'no':
                    ack = raw_input('# Are you sure you want to delete this backup definition? (yes/no): ')

                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            if ack.lower() == 'yes':
                if def_id.isdigit():
                    try:
                        if force_deletion == 'y':
                            self.db.delete_force_backup_definition_id(def_id)
                            print '[DONE] Backup definition for DefID: ' + str(def_id) +' deleted with force.\n'

                        elif force_deletion == 'n':
                            self.db.delete_backup_definition_id(def_id)
                            print '[DONE] Backup definition for DefID: ' + str(def_id) +' deleted.\n'

                    except Exception as e:
                        self.processing_error('[ERROR]: Could not delete this backup job definition\n' + str(e) + '\n')

                else:
                    self.processing_error('[ERROR]: [' + def_id + '] is not a legal value for a backup job definition\n')

            elif ack.lower() == 'no':
                print '[ABORTED] Command interrupted by the user.\n'

        #
        # Command with parameters
        #

        elif len(arg_list) == 1:
            def_id = arg_list[0]

            if def_id.isdigit():
                try:
                    self.db.delete_backup_definition_id(def_id)
                    print '[DONE] Backup definition for DefID: ' + str(def_id) +' deleted.\n'

                except Exception as e:
                    self.processing_error('[ERROR]: Could not delete this backup job definition\n' + str(e) + '\n')

            else:
                self.processing_error('[ERROR]: [' + def_id + '] is not a legal value for a backup job definition\n')

        elif len(arg_list) == 2:
            def_id = arg_list[0]

            if arg_list[1] == 'force-deletion':

                if def_id.isdigit():
                    try:
                        self.db.delete_force_backup_definition_id(def_id)
                        print '[DONE] Backup definition for DefID: ' + str(def_id) +' deleted with force.\n'

                    except Exception as e:
                        self.processing_error('[ERROR]: Could not delete this backup job definition\n' + str(e) + '\n')

                else:
                    self.processing_error('[ERROR]: [' + def_id +'] is not a legal value for a backup job definition\n')

            else:
                self.processing_error('[ERROR] - [' + arg_list[1] + '] is not a valid parameter\n')

        #
        # Command with the wrong number of parameters
        #

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or \? to list commands\n')

        print


    # ################################################
    # Method do_delete_backup_definition_database
    # ################################################

    def do_delete_backup_definition_dbname(self,args):
        '''
        DESCRIPTION:
        This command deletes all backup definitions for a database

        NOTE: You have to use the parameter force-deletion
        if you want to force the deletion of backup definitions
        with active backups in the catalog

        If you use force-deletion, all backups in the catalog for
        the backup definition deleted, will be deleted regardless of
        the retention period or retention redundancy used.

        *** Use with precaution ***

        COMMAND:
        delete_backup_definition_dbname [NodeID/FQDN]
                                        [DBname]
                                        [force-deletion]

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            ack = ''
            force_deletion = ''

            try:
                print '--------------------------------------------------------'
                pgsql_node_id = raw_input('# NodeID / FQDN: ')
                dbname = raw_input('# DBname: ')

                while force_deletion != 'y' and force_deletion != 'n':
                    force_deletion = raw_input('# Force deletion (y/n): ')

                print

                while ack != 'yes' and ack != 'no':
                    ack = raw_input('# Are you sure you want to delete this backup definition? (yes/no): ')

                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user\n'
                return False

            if ack.lower() == 'yes':

                try:
                    if pgsql_node_id.isdigit():
                        if force_deletion == 'y':
                            self.db.delete_force_backup_definition_dbname(pgsql_node_id,dbname)
                            print '[DONE] Backup definition for DBname: [' + str(dbname) + '] deleted with force.\n'

                        elif force_deletion == 'n':
                            self.db.delete_backup_definition_dbname(pgsql_node_id,dbname)
                            print '[DONE] Backup definition for DBname: [' + str(dbname) + '] deleted.\n'

                    else:
                        if force_deletion == 'y':
                            self.db.delete_force_backup_definition_dbname(self.db.get_pgsql_node_id(pgsql_node_id),dbname)
                            print '[DONE] Backup definition for DBname: [' + str(dbname) + '] deleted with force.\n'


                        elif force_deletion == 'n':
                            self.db.delete_backup_definition_dbname(self.db.get_pgsql_node_id(pgsql_node_id),dbname)
                            print '[DONE] Backup definition for DBname: [' + str(dbname) + '] deleted.\n'

                except Exception as e:
                    self.processing_error('[ERROR]: Could not delete this backup job definition\n' + str(e) + '\n')

            elif ack.lower() == 'no':
                print '[ABORTED] Command interrupted by the user.\n'

        #
        # Command with parameters
        #

        elif len(arg_list) == 2:
            pgsql_node_id = arg_list[0]
            dbname = arg_list[1]

            try:
                if pgsql_node_id.isdigit():
                    self.db.delete_backup_definition_dbname(pgsql_node_id,dbname)
                    print '[DONE] Backup definition for DBname: [' + str(dbname) + '] deleted.\n'

                else:
                    self.db.delete_backup_definition_dbname(self.db.get_pgsql_node_id(pgsql_node_id),dbname)
                    print '[DONE] Backup definition for DBname: [' + str(dbname) + '] deleted.\n'

            except Exception as e:
                self.processing_error('[ERROR]: Could not delete this backup job definition\n' + str(e) + '\n')

        elif len(arg_list) == 3:
            pgsql_node_id = arg_list[0]
            dbname = arg_list[1]

            if arg_list[2] == 'force-deletion':

                try:
                    if pgsql_node_id.isdigit():
                        self.db.delete_force_backup_definition_dbname(pgsql_node_id,dbname)
                        print '[DONE] Backup definition for DBname: [' + str(dbname) + '] deleted with force.\n'

                    else:
                        self.db.delete_force_backup_definition_dbname(self.db.get_pgsql_node_id(pgsql_node_id),dbname)
                        print '[DONE] Backup definition for DBname: [' + str(dbname) + '] deleted with force.\n'

                except Exception as e:
                    self.processing_error('[ERROR]: Could not delete this backup job definition\n' + str(e) + '\n')

            else:
                self.processing_error('[ERROR] - ' + erg_list[2] + 'is not a valid parameter\n')

        #
        # Command with the wrong number of parameters
        #

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or \? to list commands\n')

        print


    # ############################################
    # Method do_show_backup_catalog
    # ############################################

    def do_show_backup_catalog(self,args):
        '''DESCRIPTION:
        This command shows all backup catalog entries for a particular
        combination of search values.

        COMMAND:
        show_backup_catalog [SrvID|FQDN]
                            [NodeID|FQDN]
                            [DBname]
                            [DefID]
                            [Status]

        [SrvID | FQDN]:
        ---------------
        SrvID in PgBackMan or FQDN of the backup server that run the
        backup job. One can use 'all' or '*' with this parameter.

        [NodeID | FQDN]:
        ----------------
        NodeID in PgBackMan or FQDN of the PgSQL node running the
        database. One can use 'all' or '*' with this parameter.

        [Dbname]:
        ---------
        Database name. One can use 'all' or '*' with this parameter.

        [DefID]:
        --------
        Backup definition ID. One can use 'all' or '*' with this
        parameter.

        [Status]:
        ---------
        SUCCEEDED: Execution finished without error.
        ERROR: Execution finished with errors.

        One can use 'all' or '*' with this parameter.

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Default backup server
        #

        default_backup_server = self.get_default_backup_server()

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            try:
                print '--------------------------------------------------------'
                server_id = raw_input('# SrvID / FQDN [' + default_backup_server + ']: ')
                node_id = raw_input('# NodeID / FQDN [all]: ')
                dbname = raw_input('# DBname [all]: ')
                def_id = raw_input('# DefID [all]: ')
                status = raw_input('# Status [all]: ')
                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            if server_id == '':
                server_id = default_backup_server

            if server_id.lower() in ['all','*']:
                server_list = None
            else:
                server_list = server_id.strip().replace(' ','').split(',')

            if node_id.lower() in ['all','*','']:
                node_list = None
            else:
                node_list = node_id.strip().replace(' ','').split(',')

            if dbname.lower() in ['all','*','']:
                dbname_list = None
            else:
                dbname_list = dbname.strip().replace(' ','').split(',')

            if def_id.lower() in ['all','*','']:
                def_id_list = None
            else:
                def_id_list = def_id.strip().replace(' ','').split(',')

            if status.lower() in ['all','*','']:
                status_list = None
            else:
                status_list = status.strip().replace(' ','').upper().split(',')

            try:
                result = self.db.show_backup_catalog(server_list,node_list,dbname_list,def_id_list,status_list)

                colnames = [desc[0] for desc in result.description]
                self.generate_output(result,colnames,["Finished","Backup server","PgSQL node","DBname","Size"],'backup_catalog')

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')

        #
        # Command with parameters
        #

        elif len(arg_list) == 5:

            server_id = arg_list[0]
            node_id = arg_list[1]
            dbname = arg_list[2]
            def_id = arg_list[3]
            status = arg_list[4]

            if server_id == '':
                server_id = default_backup_server

            if server_id.lower() in ['all','*']:
                server_list = None
            else:
                server_list = server_id.strip().replace(' ','').split(',')

            if node_id.lower() in ['all','*','']:
                node_list = None
            else:
                node_list = node_id.strip().replace(' ','').split(',')

            if dbname.lower() in ['all','*','']:
                dbname_list = None
            else:
                dbname_list = dbname.strip().replace(' ','').split(',')

            if def_id.lower() in ['all','*','']:
                def_id_list = None
            else:
                def_id_list = def_id.strip().replace(' ','').split(',')

            if status.lower() in ['all','*','']:
                status_list = None
            else:
                status_list = status.strip().replace(' ','').upper().split(',')

            if self.output_format == 'table':

                print '--------------------------------------------------------'
                print '# SrvID / FQDN: ' + str(server_id)
                print '# NodeID / FQDN: ' + str(node_id)
                print '# DBname: ' + str(dbname)
                print '# DefID: ' + str(def_id)
                print '# Status: ' + str(status)
                print '--------------------------------------------------------'

            try:
                result = self.db.show_backup_catalog(server_list,node_list,dbname_list,def_id_list,status_list)

                colnames = [desc[0] for desc in result.description]
                self.generate_output(result,colnames,["Finished","Backup server","PgSQL node","DBname","Size"],'backup_catalog')

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        print


    # ############################################
    # Method do_show_restore_catalog
    # ############################################

    def do_show_restore_catalog(self,args):
        '''DESCRIPTION:
        This command shows all restore catalog entries for a particular
        combination of parameters values.

        COMMAND:
        show_restore_catalog [SrvID|FQDN]
                             [Target NodeID|FQDN]
                             [Target DBname]


        [SrvID|FQDN]:
        -------------
        SrvID in PgBackMan or FQDN of the backup server. One can use
        'all' or '*' with this parameter.

        [Target NodeID|FQDN]:
        ---------------------
        NodeID in PgBackMan or FQDN of the PgSQL node. One can use
        'all' or '*' with this parameter.

        [Target DBname]:
        ----------------
        Database name. One can use 'all' or '*' with this parameter.

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Default backup server
        #

        default_backup_server = self.get_default_backup_server()

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            try:
                print '--------------------------------------------------------'
                server_id = raw_input('# SrvID / FQDN [' + default_backup_server + ']: ')
                node_id = raw_input('# Target NodeID / FQDN [all]: ')
                dbname = raw_input('# Target DBname [all]: ')
                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            if server_id == '':
                server_id = default_backup_server

            if server_id.lower() in ['all','*']:
                server_list = None
            else:
                server_list = server_id.strip().replace(' ','').split(',')

            if node_id.lower() in ['all','*','']:
                node_list = None
            else:
                node_list = node_id.strip().replace(' ','').split(',')

            if dbname.lower() in ['all','*','']:
                dbname_list = None
            else:
                dbname_list = dbname.strip().replace(' ','').split(',')

            try:
                result = self.db.show_restore_catalog(server_list,node_list,dbname_list)

                colnames = [desc[0] for desc in result.description]
                self.generate_output(result,colnames,["Finished","Backup server","Target PgSQL node","Target DBname"],'restore_catalog')

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')

        #
        # Command with parameters
        #

        elif len(arg_list) == 3:

            server_id = arg_list[0]
            node_id = arg_list[1]
            dbname = arg_list[2]

            if server_id == '':
               server_id = default_backup_server

            if server_id.lower() in ['all','*']:
                server_list = None
            else:
                server_list = server_id.strip().replace(' ','').split(',')

            if node_id.lower() in ['all','*','']:
                node_list = None
            else:
                node_list = node_id.strip().replace(' ','').split(',')

            if dbname.lower() in ['all','*','']:
                dbname_list = None
            else:
                dbname_list = dbname.strip().replace(' ','').split(',')

            if self.output_format == 'table':

                print '--------------------------------------------------------'
                print '# SrvID / FQDN: ' + str(server_id)
                print '# NodeID / FQDN: ' + str(node_id)
                print '# DBname: ' + str(dbname)
                print '--------------------------------------------------------'

            try:
                result = self.db.show_restore_catalog(server_list,node_list,dbname_list)

                colnames = [desc[0] for desc in result.description]
                self.generate_output(result,colnames,["Finished","Backup server","Target PgSQL node","Target DBname"],'restore_catalog')

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        print


    # ############################################
    # Method do_register_snapshot_definition
    # ############################################

    def do_register_snapshot_definition(self,args):
        '''DESCRIPTION:
        This command registers a one time snapshot backup of a database.

        COMMAND:
        register_snapshot_definition [SrvID | FQDN]
                                     [NodeID | FQDN]
                                     [DBname]
                                     [DBname exceptions]
                                     [AT time]
                                     [backup code]
                                     [retention period]
                                     [extra backup parameters]
                                     [tag]
                                     [pg_dump/all release]

        [SrvID | FQDN]:
        ---------------
        SrvID in PgBackMan or FQDN of the backup server that will run the
        snapshot job.

        [NodeID | FQDN]:
        ----------------
        NodeID in PgBackMan or FQDN of the PgSQL node running the
        database to backup.

        [DBname]:
        ---------
        Database name.

        One can use this special value, '#all_databases#' if you
        want to register the snapshot backup for *all databases*
        in the cluster (except 'template0','template1' and 'postgres').

        [DBname exceptions]
        -------------------
        Databases that will not be considered when using
        '#all_databases#' in [DBname].

        One can define several DBnames in a comma separated list.

        [time]:
        -------
        Timestamp to run the snapshot, e.g. 2014-04-23 16:01

        [backup code]:
        --------------
        CLUSTER: Backup of all databases in a PgSQL node
        FULL: Full Backup of a database. Schema + data + owner globals + DB globals.
        SCHEMA: Schema backup of a database. Schema + owner globals + DB globals.
        DATA: Data backup of the database.

        [retention period]:
        -------------------
        Time interval, e.g. 2 hours, 3 days, 1 week, 1 month, 2 years, ...

        [extra backup parameters]:
        --------------------------
        Extra parameters that can be used with pg_dump / pg_dumpall

        [tag]:
        ------
        Define a tag for this snapshot registration. This value can be helpful when
        we register a snapshot for many databases at the same time. This
        tag can be used later when registering a backup recovery for all the
        databases from the same snapshot registration.

        If no value is defined, the system will generate a random alphanumeric tag.

        [pg_dump/all release]
        ---------------------
        Release of pg_dump / pg_dumpall to use when taking the
        snapshot, e.g. 9.0, 9.1, 9.2, 9.3 or 9.4, 9.5, 9.6 or 10. This
        parameter can be necessary if we are going to restore the
        snapshot in a postgreSQL installation running a newer release
        than the source.

        This release version cannot be lower than the one used in the
        source installation running the database we are going to
        backup.

        The release of the source installation will be used per
        default if this parameter is not defined.

        '''

        database_list = []

        #
        # Define a default tag to use with this
        # snapshot definition
        #

        x = hashlib.md5()
        x.update(str(random.randint(1, 1000000)))
        tag_default = x.hexdigest()[1:10].upper()

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Default backup server
        #

        default_backup_server = self.get_default_backup_server()

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            ack = ''

            try:
                print '--------------------------------------------------------'
                backup_server = raw_input('# Backup server SrvID / FQDN [' + default_backup_server+ ']: ').strip()
                pgsql_node = raw_input('# PgSQL node NodeID / FQDN []: ').strip()

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            try:

                if backup_server == '':
                    backup_server = default_backup_server

                if backup_server.isdigit():
                    backup_server_id = backup_server
                    backup_server_fqdn = self.db.get_backup_server_fqdn(backup_server)
                else:
                    backup_server_id = self.db.get_backup_server_id(backup_server)
                    backup_server_fqdn = backup_server

                if pgsql_node.isdigit():
                    pgsql_node_id = pgsql_node
                    pgsql_node_fqdn = self.db.get_pgsql_node_fqdn(pgsql_node)
                else:
                    pgsql_node_id = self.db.get_pgsql_node_id(pgsql_node)
                    pgsql_node_fqdn = pgsql_node

            except Exception as e:
                print '--------------------------------------------------------'
                self.processing_error('[ERROR]: ' + str(e) + '\n')
                return False

            try:
                at_time_default = datetime.datetime.now()+ datetime.timedelta(minutes=1)
                backup_code_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_code')
                retention_period_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'retention_period')
                extra_backup_parameters_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'extra_backup_parameters')

            except Exception as e:
                print '\n--------------------------------------------------------'
                self.processing_error('[ERROR]: Problems getting default values for parameters\n' + str(e) + '\n')
                return False

            try:
                dbname = raw_input('# DBname []: ')
                dbname_exceptions = raw_input('# DBname exceptions []: ')
                at_time = raw_input('# AT timestamp [' + str(at_time_default) + ']: ')
                backup_code = raw_input('# Backup code [' + backup_code_default + ']: ')
                retention_period = raw_input('# Retention period [' + retention_period_default + ']: ')
                extra_backup_parameters = raw_input('# Extra parameters [' + extra_backup_parameters_default + ']: ')
                remarks = raw_input('# Tag [' + tag_default + ']: ')
                pg_dump_release = raw_input('# pg_dump/all release [Same as pgSQL node running dbname]: ')
                print

                while ack != 'yes' and ack != 'no':
                    ack = raw_input('# Are all values correct (yes/no): ')

                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            if ack.lower() == 'yes':

                if at_time == '':
                    at_time = at_time_default

                if backup_code == '':
                    backup_code = backup_code_default

                if retention_period == '':
                    retention_period = retention_period_default

                if extra_backup_parameters == '':
                    extra_backup_parameters = extra_backup_parameters_default

                if remarks == '':
                    remarks = tag_default

                if pg_dump_release.strip() == '':
                    pg_dump_release = None

                elif pg_dump_release not in ('9.0', '9.1', '9.2', '9.3', '9.4', '9.5', '9.6','10'):
                    self.processing_error('[ERROR]: pg_dump/all release [' + str(pg_dump_release).strip() + '] is not valid\n')

                try:
                    self.db.check_pgsql_node_status(pgsql_node_id)

                    dsn_value = self.db.get_pgsql_node_dsn(pgsql_node_id)
                    db_node = PgbackmanDB(dsn_value, 'pgbackman_cli')

                    dbname_exceptions_list = dbname_exceptions.replace(' ','').split(',')

                    #
                    # Generating a list of databases that will get a backup definition
                    #

                    if dbname == '#all_databases#':

                        for database in db_node.get_pgsql_node_database_list():

                            if database[0] not in dbname_exceptions_list:
                                database_list.append(database[0])

                    else:
                        database_list = dbname.strip().replace(' ','').split(',')

                except Exception as e:
                    self.processing_error('[ERROR]: ' + str(e) + '\n')
                    return False


                #
                # Loop through the list of databases that will get a backup definition
                #

                for index, database in enumerate(database_list):

                    error = False

                    #
                    # Check if the database exists in the PgSQL node
                    #

                    if database != '' and database != '#all_databases#':

                        try:
                            if not db_node.database_exists(database):
                                self.processing_error('[ERROR]: Database [' + database + '] does not exist in The PgSQL node [' + pgsql_node_fqdn + ']')

                                error = True

                        except Exception as e:
                            self.processing_error('[ERROR]: ' + str(e) + '\n')

                            error = True

                    try:

                        if error == False:

                            self.db.register_snapshot_definition(backup_server_id,pgsql_node_id,database.strip(),at_time,backup_code.upper().strip(), \
                                                                 retention_period.lower().strip(),extra_backup_parameters.lower().strip(),remarks.strip(), \
                                                                 pg_dump_release)

                            print '[DONE] Snapshot for dbname: [' + database.strip() + '] and backup code [' + backup_code.upper() + '] defined.\n'

                    except Exception as e:
                        self.processing_error('[ERROR]: Could not register this snapshot\n' + str(e) + '\n')

            elif ack.lower() == 'no':
                print '[ABORTED] Command interrupted by the user.\n'

        #
        # Command with parameters
        #

        elif len(arg_list) == 10:

            backup_server = arg_list[0]
            pgsql_node = arg_list[1]

            try:

                if backup_server == '':
                    backup_server = default_backup_server

                if backup_server.isdigit():
                    backup_server_id = backup_server
                    backup_server_fqdn = self.db.get_backup_server_fqdn(backup_server)
                else:
                    backup_server_id = self.db.get_backup_server_id(backup_server)
                    backup_server_fqdn = backup_server

                if pgsql_node.isdigit():
                    pgsql_node_id = pgsql_node
                    pgsql_node_fqdn = self.db.get_pgsql_node_fqdn(pgsql_node)
                else:
                    pgsql_node_id = self.db.get_pgsql_node_id(pgsql_node)
                    pgsql_node_fqdn = pgsql_node

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')
                return False

            try:
                at_time_default = datetime.datetime.now()+ datetime.timedelta(minutes=1)
                backup_code_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_code')
                retention_period_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'retention_period')
                extra_backup_parameters_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'extra_backup_parameters')

            except Exception as e:

                self.processing_error('[ERROR]: Problems getting default values for parameters\n' + str(e) + '\n')
                return False

            dbname = arg_list[2]
            dbname_exceptions = arg_list[3]
            at_time = str(arg_list[4])
            backup_code = arg_list[5]
            retention_period = arg_list[6]
            extra_backup_parameters = arg_list[7]
            remarks = arg_list[8]
            pg_dump_release = arg_list[9]

            if at_time == '':
                at_time = at_time_default

            if backup_code == '':
                backup_code = backup_code_default

            if retention_period == '':
                retention_period = retention_period_default

            if extra_backup_parameters == '':
                extra_backup_parameters = extra_backup_parameters_default

            if remarks == '':
                remarks = tag_default

            if pg_dump_release.strip() == '':
                pg_dump_release = None

            elif pg_dump_release not in ('9.0', '9.1', '9.2', '9.3', '9.4', '9.5', '9.6','10'):
                self.processing_error('[ERROR]: pg_dump/all release [' + str(pg_dump_release).strip() + '] is not valid\n')

            try:
                self.db.check_pgsql_node_status(pgsql_node_id)

                dsn_value = self.db.get_pgsql_node_dsn(pgsql_node_id)
                db_node = PgbackmanDB(dsn_value, 'pgbackman_cli')

                dbname_exceptions_list = dbname_exceptions.replace(' ','').split(',')

                #
                # Generating a list of databases that will get a backup definition
                #

                if dbname == '#all_databases#':

                    for database in db_node.get_pgsql_node_database_list():

                        if database[0] not in dbname_exceptions_list:
                            database_list.append(database[0])

                else:
                    database_list = dbname.strip().replace(' ','').split(',')

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')
                return False


            #
            # Loop through the list of databases that will get a backup definition
            #

            for index, database in enumerate(database_list):

                error = False

                #
                # Check if the database exists in the PgSQL node
                #

                if database != '' and database != '#all_databases#':

                    try:
                        if not db_node.database_exists(database):
                            self.processing_error('[ERROR]: Database [' + database + '] does not exist in The PgSQL node [' + pgsql_node_fqdn + ']')

                            error = True

                    except Exception as e:
                        self.processing_error('[ERROR]: ' + str(e) + '\n')

                        error = True

                try:

                    if error == False:

                        self.db.register_snapshot_definition(backup_server_id,pgsql_node_id,database.strip(),at_time,backup_code.upper().strip(), \
                                                             retention_period.lower().strip(),extra_backup_parameters.lower().strip(),remarks.strip(), \
                                                             pg_dump_release)

                        print '[DONE] Snapshot for dbname: [' + database.strip() + '] and backup code [' + backup_code.upper() + '] defined.\n'

                except Exception as e:
                    self.processing_error('[ERROR]: Could not register this snapshot\n' + str(e) + '\n')

        #
        # Command with the wrong number of parameters
        #

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or \? to list commands\n')

        print


    # ############################################
    # Method do_show_snapshot_definitions
    # ############################################

    def do_show_snapshot_definitions(self,args):
        '''DESCRIPTION:

        This command shows all snapshot definitions for a particular
        combination of parameter values.

        Status:
        -------
        WAITING: Waiting to define an AT job to run this snapshot
        DEFINED: AT job for this snapshot has been defined
        ERROR:   Could not define the AT job for this snapshot.

        COMMAND:
        show_snapshot_definitions [SrvID|FQDN]
                                  [NodeID|FQDN]
                                  [DBname]

        [SrvID|FQDN]:
        -------------
        SrvID in PgBackMan or FQDN of the backup server. One can use
        'all' or '*' with this parameter.

        [NodeID|FQDN]:
        --------------
        NodeID in PgBackMan or FQDN of the PgSQL node. One can use
        'all' or '*' with this parameter.

        [DBname]:
        ---------
        Database name. One can use 'all' or '*' with this parameter.

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Default backup server
        #

        default_backup_server = self.get_default_backup_server()

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            try:
                print '--------------------------------------------------------'
                server_id = raw_input('# SrvID / FQDN [' + default_backup_server+ ']: ')
                node_id = raw_input('# NodeID / FQDN [all]: ')
                dbname = raw_input('# DBname [all]: ')
                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            if server_id == '':
                server_id = default_backup_server

            if server_id.lower() in ['all','*']:
                server_list = None
            else:
                server_list = server_id.strip().replace(' ','').split(',')

            if node_id.lower() in ['all','*','']:
                node_list = None
            else:
                node_list = node_id.strip().replace(' ','').split(',')

            if dbname.lower() in ['all','*','']:
                dbname_list = None
            else:
                dbname_list = dbname.strip().replace(' ','').split(',')

            try:
                result = self.db.show_snapshot_definitions(server_list,node_list,dbname_list)

                colnames = [desc[0] for desc in result.description]
                self.generate_output(result,colnames,["Backup server","PgSQL node","DBname","AT time","Parameters"],'snapshot_definitions')

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')

        #
        # Command with parameters
        #

        elif len(arg_list) == 3:

            server_id = arg_list[0]
            node_id = arg_list[1]
            dbname = arg_list[2]

            if server_id == '':
                server_id = default_backup_server

            if server_id.lower() in ['all','*']:
                server_list = None
            else:
                server_list = server_id.strip().replace(' ','').split(',')

            if node_id.lower() in ['all','*','']:
                node_list = None
            else:
                node_list = node_id.strip().replace(' ','').split(',')

            if dbname.lower() in ['all','*','']:
                dbname_list = None
            else:
                dbname_list = dbname.strip().replace(' ','').split(',')

            if self.output_format == 'table':

                print '--------------------------------------------------------'
                print '# SrvID / FQDN: ' + str(server_id)
                print '# NodeID / FQDN: ' + str(node_id)
                print '# DBname: ' + str(dbname)
                print '--------------------------------------------------------'

            try:
                result = self.db.show_snapshot_definitions(server_list,node_list,dbname_list)

                colnames = [desc[0] for desc in result.description]
                self.generate_output(result,colnames,["Backup server","PgSQL node","DBname","AT time","Parameters"],'snapshot_definitions')

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')

        #
        # Command with the wrong number of parameters
        #

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        print


    # ############################################
    # Method do_register_restore_definition
    # ############################################

    def do_register_restore_definition(self,args):
        '''
        DESCRIPTION:
        This command defines a restore job of a backup from the
        catalog. Nowadays it can only restore automatically backups
        with code FULL (Schema + data). It can be run only
        interactively.

        COMMAND:
        register_restore_definition

        [AT time]:
        -------
        Timestamp to run the restore job

        [BckID]:
        --------
        ID of the backup to restore

        [Target NodeID | FQDN]:
        -----------------------
        PgSQL node ID or FQDN where we want to restore the backup

        [Target DBname]:
        ----------------
        Database name where we want to restore the backup. The default
        name is the DBname defined in BckID.

        [Extra parameters]:
        -------------------
        Extra parameters that can be used with pg_restore

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            ack_input = ack_rename = ack_reuse = ack_confirm = ''
            at_time = bck_id = target_dbname = renamed_dbname = None
            roles_to_restore = []

            try:
                at_time_default = datetime.datetime.now()+ datetime.timedelta(minutes=1)

            except Exception as e:
                print '--------------------------------------------------------'
                self.processing_error('[ERROR]: Problems getting default values for parameters\n' + str(e) + '\n')
                return False

            try:
                print '--------------------------------------------------------'
                at_time = raw_input('# AT timestamp [' + str(at_time_default) + ']: ')
                bck_id = raw_input('# BckID []: ')

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            try:
                if bck_id == '':
                    target_dbname_default = self.db.get_dbname_from_bckid(-1)
                else:
                    target_dbname_default = self.db.get_dbname_from_bckid(bck_id)
                    backup_server_id = self.db.get_backup_server_id_from_bckid(bck_id)
                    backup_server_fqdn = self.db.get_backup_server_fqdn(backup_server_id)
                    role_list = self.db.get_role_list_from_bckid(bck_id)

            except Exception as e:
                print '--------------------------------------------------------'
                self.processing_error('[ERROR]:' + str(e) + '\n')
                return False

            try:
                target_pgsql_node = raw_input('# Target NodeID / FQDN []: ').strip()

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            try:
                if target_pgsql_node.isdigit():
                    pgsql_node_id = target_pgsql_node
                    pgsql_node_fqdn = self.db.get_pgsql_node_fqdn(target_pgsql_node)
                else:
                    pgsql_node_id = self.db.get_pgsql_node_id(target_pgsql_node)
                    pgsql_node_fqdn = target_pgsql_node

            except Exception as e:
                print '--------------------------------------------------------'
                self.processing_error('[ERROR]: ' + str(e) + '\n')
                return False

            try:
                extra_restore_parameters_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'extra_restore_parameters')

            except Exception as e:
                print '--------------------------------------------------------'
                self.processing_error('[ERROR]: ' + str(e) + '\n')
                return False

            try:
                target_dbname = raw_input('# Target DBname [' + target_dbname_default + ']: ')
                extra_restore_parameters = raw_input('# Extra parameters [' + extra_restore_parameters_default + ']: ')
                print

                while ack_input.lower() != 'yes' and ack_input.lower() != 'no':
                    ack_input = raw_input('# Are all values correct (yes/no): ')

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            if ack_input.lower() == 'yes':

                print '\n--------------------------------------------------------'
                print '[Processing restore data]'
                print '--------------------------------------------------------'

                try:
                    if at_time == '':
                        at_time = at_time_default

                    if extra_restore_parameters == '':
                        extra_restore_parameters = extra_restore_parameters_default

                    #
                    # Check if PGnode is online.
                    # Stop the restore process if it is down.
                    #
                    self.db.check_pgsql_node_status(pgsql_node_id)

                    dsn_value = self.db.get_pgsql_node_dsn(pgsql_node_id)
                    db_node = PgbackmanDB(dsn_value, 'pgbackman_cli')

                    if target_dbname == '':
                        target_dbname = target_dbname_default

                    #
                    # Check if Target DBname already exists in PGnode.
                    # If it exists, ask if we should rename the existing database before
                    # continuing. Stop the restore process if it is not renamed.
                    #

                    if not db_node.database_exists(target_dbname):
                        print '[OK]: Target DBname ' + target_dbname + ' does not exist on target PgSQL node.'

                    else:
                        print '[WARNING]: Target DBname already exists on target PgSQL node.'

                        try:
                            while ack_rename.lower() != 'yes' and ack_rename.lower() != 'no':
                                ack_rename = raw_input('# Rename it? (yes/no): ')

                        except Exception as e:
                            print '\n--------------------------------------------------------'
                            print '[ABORTED] Command interrupted by the user.\n'
                            return False

                        if ack_rename.lower() == 'no':
                            print '[ABORTED]: Cannot continue with this restore definition without \nrenaming the existing database or using another Target DBname value'
                            return False

                        elif ack_rename.lower() == 'yes':
                            renamed_dbname_default = target_dbname + '_' + datetime.datetime.now().strftime('%Y_%m_%dT%H%M%S')

                            try:
                                renamed_dbname = raw_input('# Rename existing database to [' + renamed_dbname_default + ']: ')
                            except Exception as e:
                                print '\n--------------------------------------------------------'
                                print '[ABORTED] Command interrupted by the user.\n'
                                return False

                            if renamed_dbname == '':
                                renamed_dbname = renamed_dbname_default

                            try:
                                while db_node.database_exists(renamed_dbname):
                                    print '[WARNING]: Renamed database already exist on target PgSQL node.'
                                    renamed_dbname = raw_input('# Rename existing database to [' + renamed_dbname_default + ']: ')

                                    if renamed_dbname == '':
                                        renamed_dbname = renamed_dbname_default

                            except Exception as e:
                                print '\n--------------------------------------------------------'
                                print '[ABORTED] Command interrupted by the user.\n'
                                return False

                            print '[OK]: Renamed DBname ' + renamed_dbname + ' does not exist on target PgSQL node.'

                except Exception as e:
                    self.processing_error('[ERROR]: ' + str(e) + '\n')
                    return False

                #
                # Check if some of the roles to restore already exist in PGnode
                # If a role already exists, ask if we can use it
                # without having to restore it
                #

                for role in role_list:

                    ack_reuse = ''

                    if not db_node.role_exists(role):
                        print '[OK]: Role ' + role + ' does not exist on target PgSQL node.'
                        roles_to_restore.append(role)
                    else:
                        print '[WARNING]: Role ' + role + ' already exists on target PgSQL node.'

                        try:
                            while ack_reuse.lower() != 'yes' and ack_reuse.lower() != 'no':
                                ack_reuse = raw_input('# Use the existing role? (yes/no): ')

                        except Exception as e:
                                print '\n--------------------------------------------------------'
                                print '[ABORTED] Command interrupted by the user.\n'
                                return False

                        if ack_reuse.lower() == 'no':
                            print '[ABORTED]: Cannot continue with this restore definition when some roles we need\n to restore already exist and we can not reuse them.'
                            return False

                print '\n--------------------------------------------------------'
                print '[Restore definition accepted]'
                print '--------------------------------------------------------'
                print 'AT time: ' + str(at_time)
                print 'BckID to restore: ' + str(bck_id)
                print 'Roles to restore: ' + ', '.join(roles_to_restore)
                print 'Backup server: [' + str(backup_server_id) + '] ' + str(backup_server_fqdn)
                print 'Target PgSQL node: [' + str(pgsql_node_id) + '] ' + str(pgsql_node_fqdn)
                print 'Target DBname: ' + str(target_dbname)
                print 'Extra restore parameters: ' + str(extra_restore_parameters)
                print 'Existing database will be renamed to : ' + str(renamed_dbname)
                print '--------------------------------------------------------'

                try:
                    while ack_confirm.lower() != 'yes' and ack_confirm.lower() != 'no':
                        ack_confirm = raw_input('# Are all values correct (yes/no): ')

                    print '--------------------------------------------------------'

                except Exception as e:
                    print '\n--------------------------------------------------------'
                    print '[ABORTED] Command interrupted by the user.\n'
                    return False

                if ack_confirm.lower() == 'yes':

                    try:
                        self.db.register_restore_definition(at_time,backup_server_id,pgsql_node_id,bck_id,target_dbname,renamed_dbname,extra_restore_parameters,roles_to_restore)
                        print '[DONE] Restore definition registered.\n'

                    except Exception as e:
                        self.processing_error('[ERROR]: Could not register this restore definition\n' + str(e) + '\n')

                elif ack_confirm.lower() == 'no':
                    print '[ABORTED] Command interrupted by the user.\n'

            elif ack_input.lower() == 'no':
                print '[ABORTED] Command interrupted by the user.\n'

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        print


    # ############################################
    # Method do_show_restore_definitions
    # ############################################

    def do_show_restore_definitions(self,args):
        '''
        DESCRIPTION:
        This command shows all restore definitions for a particular
        combination of parameter values.

        Status information:
        -------------------
        WAITING: Waiting to define an AT job to run this restore job
        DEFINED: AT job for this restore job has been defined
        ERROR:   Could not define the AT job for this restore job.

        COMMAND:
        show_restore_definitions [SrvID|FQDN]
                                 [NodeID|FQDN]
                                 [DBname]

        [SrvID|FQDN]:
        -------------
        SrvID in PgBackMan or FQDN of the backup server. One can use
        'all' or '*' with this parameter.

        [NodeID|FQDN]:
        --------------
        NodeID in PgBackMan or FQDN of the PgSQL node. One can use
        'all' or '*' with this parameter.

        [DBname]:
        ---------
        Database name. One can use 'all' or '*' with this parameter.

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Default backup server
        #

        default_backup_server = self.get_default_backup_server()

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            try:
                print '--------------------------------------------------------'
                server_id = raw_input('# SrvID / FQDN [' + default_backup_server + ']: ')
                node_id = raw_input('# Target NodeID / FQDN [all]: ')
                dbname = raw_input('# Target DBname [all]: ')
                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            if server_id == '':
                server_id = default_backup_server

            if server_id.lower() in ['all','*']:
                server_list = None
            else:
                server_list = server_id.strip().replace(' ','').split(',')

            if node_id.lower() in ['all','*','']:
                node_list = None
            else:
                node_list = node_id.strip().replace(' ','').split(',')

            if dbname.lower() in ['all','*','']:
                dbname_list = None
            else:
                dbname_list = dbname.strip().replace(' ','').split(',')

            try:
                result = self.db.show_restore_definitions(server_list,node_list,dbname_list)

                colnames = [desc[0] for desc in result.description]
                self.generate_output(result,colnames,["Backup server","Target PgSQL node","Target DBname","AT time"],'restore_definitions')

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')

        #
        # Command with parameters
        #

        elif len(arg_list) == 3:

            server_id = arg_list[0]
            node_id = arg_list[1]
            dbname = arg_list[2]

            if server_id == '':
                server_id = default_backup_server

            if server_id.lower() in ['all','*']:
                server_list = None
            else:
                server_list = server_id.strip().replace(' ','').split(',')

            if node_id.lower() in ['all','*','']:
                node_list = None
            else:
                node_list = node_id.strip().replace(' ','').split(',')

            if dbname.lower() in ['all','*','']:
                dbname_list = None
            else:
                dbname_list = dbname.strip().replace(' ','').split(',')

            if self.output_format == 'table':

                print '--------------------------------------------------------'
                print '# SrvID / FQDN: ' + server_id
                print '# Target NodeID / FQDN: ' + node_id
                print '# Target DBname: ' + dbname
                print '--------------------------------------------------------'

            try:
                result = self.db.show_restore_definitions(server_list,node_list,dbname_list)

                colnames = [desc[0] for desc in result.description]
                self.generate_output(result,colnames,["Backup server","Target PgSQL node","Target DBname","AT time"],'restore_definitions')

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')

        #
        # Command with the wrong number of parameters
        #

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        print


    # ############################################
    # Method do_show_backup_details
    # ############################################

    def do_show_backup_details(self,args):
        '''
        DESCRIPTION:
        This command shows all the details for one particular backup
        job.

        COMMAND:
        show_backup_details [BckID]

        [BckID]:
        --------
        Backup ID in the backup catalog.

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            try:
                print '--------------------------------------------------------'
                bck_id = raw_input('# BckID: ')
                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            if bck_id.isdigit():
                try:
                    result = self.db.show_backup_details(bck_id)

                    if len(result) > 0:
                        self.generate_unique_output(result,'backup_details')
                    else:
                        self.processing_error('[ERROR]: BckID [' + bck_id + '] does not exist' )

                except Exception as e:
                    self.processing_error('[ERROR]: ' + str(e) + '\n')

            else:
                self.processing_error('[ERROR]: The BckID must be a digit.\n')

        #
        # Command with parameters
        #

        elif len(arg_list) == 1:

            bck_id = arg_list[0]

            if self.output_format == 'table':

                print '--------------------------------------------------------'
                print '# BckID: ' + str(bck_id)
                print '--------------------------------------------------------'

            if bck_id.isdigit():
                try:
                    result = self.db.show_backup_details(bck_id)

                    if len(result) > 0:
                        self.generate_unique_output(result,'backup_details')
                    else:
                        self.processing_error('[ERROR]: BckID [' + bck_id + '] does not exist' )

                except Exception as e:
                    self.processing_error('[ERROR]: ' + str(e) + '\n')

            else:
                self.processing_error('[ERROR]: The BckID must be a digit.\n')

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        print


    # ############################################
    # Method do_show_restore_details
    # ############################################

    def do_show_restore_details(self,args):
        '''
        DESCRIPTION:
        This command shows all the details for one particular restore
        job.

        COMMAND:
        show_restore_details [RestoreID]

        [RestoreID]:
        ------------
        Restore ID in the restore catalog.

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            try:
                print '--------------------------------------------------------'
                restore_id = raw_input('# RestoreID: ')
                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            if restore_id.isdigit():
                try:
                    result = self.db.show_restore_details(restore_id)

                    if len(result) > 0:
                        self.generate_unique_output(result,'restore_details')
                    else:
                        self.processing_error('[ERROR]: RestoreID [' + restore_id + '] does not exist' )

                except Exception as e:
                    self.processing_error('[ERROR]: ' + str(e) + '\n')

            else:
                self.processing_error('[ERROR]: The restoreID must be a digit.\n')

        #
        # Command with parameters
        #

        elif len(arg_list) == 1:

            restore_id = arg_list[0]

            if self.output_format == 'table':

                print '--------------------------------------------------------'
                print '# RestoreID: ' + str(restore_id)
                print '--------------------------------------------------------'

            if restore_id.isdigit():
                try:
                    result = self.db.show_restore_details(restore_id)

                    if len(result) > 0:
                        self.generate_unique_output(result,'restore_details')
                    else:
                        self.processing_error('[ERROR]: RestoreID [' + restore_id + '] does not exist' )

                except Exception as e:
                    self.processing_error('[ERROR]: ' + str(e) + '\n')

            else:
                self.processing_error('[ERROR]: The restoreID must be a digit.\n')

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        print


    # ############################################
    # Method do_show_pgbackman_config
    # ############################################

    def do_show_pgbackman_config(self,args):
        '''
        DESCRIPTION:

        This command shows the configuration parameters used by this
        PgBackMan shell session.

        COMMAND:
        show_pgbackman_config

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Default backup server
        #

        default_backup_server = self.get_default_backup_server()

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            try:

                result =  OrderedDict()

                result['Running modus'] = str(self.execution_modus)
                result['Backup server'] = default_backup_server
                result['Software version'] = '[' + str(self.software_version_number) + ']:' + str(self.software_version_tag).replace('.','_')
                result['Configuration file used'] = str(self.conf.config_file)
                result['#'] = ''
                result['#PGBACKMAN DATABASE'] = ''
                result['DBhost'] = str(self.conf.dbhost)
                result['DBhostaddr'] = str(self.conf.dbhostaddr)
                result['DBport'] = str(self.conf.dbport)
                result['DBname'] = str(self.conf.dbname)
                result['DBuser'] = str(self.conf.dbuser)
                result['Connection retry interval'] = str(self.conf.pg_connect_retry_interval) + ' sec.'
                result['##'] = ''
                result['Database source dir'] = str(self.conf.database_source_dir)

                database_version = self.get_pgbackman_database_version_info()

                result['DB version installed'] = str(database_version[0])
                result['DB version'] = '[' + str(database_version[1]) + ']:' + str(database_version[2]).replace('v_','')
                result['###'] = ''
                result['#PGBACKMAN_DUMP'] =''
                result['Temp directory'] = str(self.conf.tmp_dir)
                result['Pause recovery on slave node'] = str(self.conf.pause_recovery_process_on_slave)
                result['####'] = ''
                result['#PGBACKMAN_MAINTENANCE'] = ''
                result['Maintenance interval'] = str(self.conf.maintenance_interval) + ' sec.'
                result['#####'] = ''
                result['#PGBACKMAN_ALERTS'] = ''
                result['SMTP alerts activated'] = str(self.conf.smtp_alerts)
                result['Alerts check interval'] = str(self.conf.alerts_check_interval) + ' sec.'
                result['SMTP server'] = str(self.conf.smtp_server)
                result['SMTP port'] = str(self.conf.smtp_port)
                result['Use SMTP SSL'] = str(self.conf.smtp_ssl)
                result['SMTP user'] = str(self.conf.smtp_user)
                result['Default From address'] = str(self.conf.smtp_from_address)
                result['Alerts e-mail template'] = str(self.conf.alerts_template)
                result['######'] = ''
                result['#LOGGING'] = ''
                result['Log level'] = str(self.conf.log_level)
                result['Log file'] = str(self.conf.log_file)
                result['#######'] = ''
                result['#OUTPUT'] = ''
                result['Default output format'] = str(self.output_format)

                self.generate_unique_output(result,'pgbackman_config')

            except Exception as e:
                    self.processing_error('[ERROR]: ' + str(e) + '\n')

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        print


    # ############################################
    # Method do_show_pgbackman_stats
    # ############################################

    def do_show_pgbackman_stats(self,args):
        '''
        DESCRIPTION:
        This command shows global statistics for this PgBackMan
        installation

        COOMAND:
        show_pgbackman_stats

        '''
        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        if len(arg_list) == 0:
            try:
                result = self.db.show_pgbackman_stats()

                self.generate_unique_output(result,'pgbackman_stats')

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')
        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        print


    # ############################################
    # Method do_show_backup_server_stats
    # ############################################

    def do_show_backup_server_stats(self,args):
        '''
        DESCRIPTION:
        This command shows global statistics for a backup server

        COMMAND:
        show_backup_server_stats [SrvID | FQDN]

        [SrvID | FQDN]:
        ---------------
        SrvID in PgBackMan or FQDN of the backup server

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Default backup server
        #

        default_backup_server = self.get_default_backup_server()

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            try:
                print '--------------------------------------------------------'
                server_id = raw_input('# SrvID / FQDN [' + default_backup_server + ']: ')
                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            try:

                if server_id == '':
                    server_id = default_backup_server

                if server_id.isdigit():
                    backup_server_id = server_id
                else:
                    backup_server_id = self.db.get_backup_server_id(server_id)

                result = self.db.show_backup_server_stats(backup_server_id)

                if len(result) > 0:
                    self.generate_unique_output(result,'backup_server_stats')
                else:
                    self.processing_error('[ERROR]: SrvID [' + backup_server_id + '] does not exist' )

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')

        #
        # Command with parameters
        #

        elif len(arg_list) == 1:

            server_id = arg_list[0]

            if server_id == '':
                server_id = default_backup_server

            if self.output_format == 'table':

                print '--------------------------------------------------------'
                print '# SrvID: ' + server_id
                print '--------------------------------------------------------'

            try:
                if server_id.isdigit():
                    backup_server_id = server_id
                else:
                    backup_server_id = self.db.get_backup_server_id(server_id)

                result = self.db.show_backup_server_stats(backup_server_id)

                if len(result) > 0:
                    self.generate_unique_output(result,'backup_server_stats')
                else:
                    self.processing_error('[ERROR]: SrvID [' + backup_server_id + '] does not exist' )

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        print


    # ############################################
    # Method do_show_pgsql_node_stats
    # ############################################

    def do_show_pgsql_node_stats(self,args):
        '''
        DESCRIPTION:
        This command shows global statistics for a PgSQL node

        COMMAND:
        show_pgsql_node_stats [NodeID | FQDN]

        [NodeID|FQDN]:
        --------------
        NodeID in PgBackMan or FQDN of the PgSQL node

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            try:
                print '--------------------------------------------------------'
                node_id = raw_input('# NodeID / FQDN: ')
                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            try:

                if node_id.isdigit():
                    pgsql_node_id = node_id
                else:
                    pgsql_node_id = self.db.get_pgsql_node_id(node_id)

                result = self.db.show_pgsql_node_stats(pgsql_node_id)

                if len(result) > 0:
                    self.generate_unique_output(result,'pgsql_node_stats')
                else:
                    self.processing_error('[ERROR]: NodeID [' + pgsql_node_id + '] does not exist' )

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')

        #
        # Command with parameters
        #

        elif len(arg_list) == 1:

            node_id = arg_list[0]

            if self.output_format == 'table':

                print '--------------------------------------------------------'
                print '# NodeID: ' + str(node_id)
                print '--------------------------------------------------------'

            try:
                if node_id.isdigit():
                    pgsql_node_id = node_id
                else:
                    pgsql_node_id = self.db.get_pgsql_node_id(node_id)

                result = self.db.show_backup_server_stats(pgsql_node_id)

                if len(result) > 0:
                    self.generate_unique_output(result,'pgsql_node_stats')
                else:
                    self.processing_error('[ERROR]: NodeID [' + pgsql_node_id + '] does not exist' )

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        print


    # ############################################
    # Method do_show_job_queue
    # ############################################

    def do_show_jobs_queue(self,args):
        '''
        DESCRIPTION:
        This command shows the queue of jobs waiting
        to be processed by pgbackman_control

        COMMAND:
        show_jobs_queue

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        if len(arg_list) == 0:
            try:
                result = self.db.show_jobs_queue()

                colnames = [desc[0] for desc in result.description]
                self.generate_output(result,colnames,["JobID","Registered","Backup server","PgSQL node"],'jobs_queue')

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')

        else:
            self.processing_error('\n[ERROR] - This command does not accept parameters.\n          Type help or ? to list commands\n')

        print


    # ############################################
    # Method do_show_backup_server_config
    # ############################################

    def do_show_backup_server_config(self,args):
        '''
        DESCRIPTION:
        This command shows the default configuration for a backup
        server

        COMMAND:
        show_backup_server_config [SrvID | FQDN]

        [SrvID | FQDN]:
        ---------------
        SrvID in PgBackMan or FQDN of the backup server

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Default backup server
        #

        default_backup_server = self.get_default_backup_server()

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            try:
                print '--------------------------------------------------------'
                server_id = raw_input('# SrvID / FQDN [' + default_backup_server + ']: ')
                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            try:

                if server_id == '':
                    server_id = default_backup_server

                if server_id.isdigit():
                    backup_server_id = server_id
                else:
                    backup_server_id = self.db.get_backup_server_id(server_id)

                result = self.db.show_backup_server_config(backup_server_id)

                colnames = [desc[0] for desc in result.description]
                self.generate_output(result,colnames,["Parameter","Value","Description"],'backup_server_config')

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')

        #
        # Command with parameters
        #

        elif len(arg_list) == 1:

            server_id = arg_list[0]

            if server_id == '':
                server_id = default_backup_server

            if self.output_format == 'table':

                print '--------------------------------------------------------'
                print '# SrvID / FQDN: ' + server_id
                print '--------------------------------------------------------'

            try:

                if server_id.isdigit():
                    backup_server_id = server_id
                else:
                    backup_server_id = self.db.get_backup_server_id(server_id)

                result = self.db.show_backup_server_config(backup_server_id)

                colnames = [desc[0] for desc in result.description]
                self.generate_output(result,colnames,["Parameter","Value","Description"],'backup_server_config')

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        print


    # ############################################
    # Method do_show_pgsql_node_config
    # ############################################

    def do_show_pgsql_node_config(self,args):
        '''
        DESCRIPTION:
        This command shows the default configuration
        for a PgSQL node

        COMMAND
        show_pgsql_node_config [NodeID | FQDN]

        [NodeID | FQDN]:
        ----------------
        NodeID in PgBackMan or FQDN of the PgSQL node

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            try:
                print '--------------------------------------------------------'
                node_id = raw_input('# NodeID / FQDN: ')
                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            try:

                if node_id.isdigit():
                    pgsql_node_id = node_id
                else:
                    pgsql_node_id = self.db.get_pgsql_node_id(node_id)

                result = self.db.show_pgsql_node_config(pgsql_node_id)

                colnames = [desc[0] for desc in result.description]
                self.generate_output(result,colnames,["Parameter","Value","Description"],'pgsql_node_config')

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')

        #
        # Command with parameters
        #

        elif len(arg_list) == 1:

            node_id = arg_list[0]

            if self.output_format == 'table':

                print '--------------------------------------------------------'
                print '# NodeID / FQDN: ' + str(node_id)
                print '--------------------------------------------------------'

            try:

                if node_id.isdigit():
                    pgsql_node_id = node_id
                else:
                    pgsql_node_id = self.db.get_pgsql_node_id(node_id)

                result = self.db.show_pgsql_node_config(pgsql_node_id)

                colnames = [desc[0] for desc in result.description]
                self.generate_output(result,colnames,["Parameter","Value","Description"],'pgsql_node_config')

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        print


    # ############################################
    # Method do_show_empty_backup_catalogs
    # ############################################

    def do_show_empty_backup_catalogs(self,args):
        '''
        DESCRIPTION:
        This command shows a list with all backup definitions with
        empty catalogs

        COMMAND:
        show_empty_backup_catalogs

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        if len(arg_list) == 0:
            try:
                result = self.db.show_empty_backup_catalogs()

                colnames = [desc[0] for desc in result.description]
                self.generate_output(result,colnames,["Backup server","PgSQL node","Schedule","Retention","Parameters"],'empty_backup_catalogs')

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')

        else:
            self.processing_error('\n[ERROR] - This command does not accept parameters.\n          Type help or ? to list commands\n')

        print


    # ###################################################
    # Method do_show_databases_without_backup_definitions
    # ###################################################

    def do_show_databases_without_backup_definitions(self,args):
        '''DESCRIPTION:

        This command shows all databases in a PgSQL node without a
        backup definition.

        COMMAND:
        show_databases_without_backup_definitions [Node ID | FQDN]

        [Node ID | FQDN]
        ----------------
        NodeID in PgBackMan or FQDN of the PgSQL node. One can use
        'all' or '*' with this parameter.

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            try:
                print '--------------------------------------------------------'
                pgsql_node = raw_input('# NodeID / FQDN: ').lower()
                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            try:

                result = self.db.show_databases_without_backup_definitions(pgsql_node)

                colnames = ['PgSQL node','DBname']
                self.generate_output(result,colnames,["PgSQL node","DBname"],'databases_without_backup_definitions')

            except Exception as e:
                print '--------------------------------------------------------'
                self.processing_error('[ERROR]: ' + str(e) + '\n')
                return False

        #
        # Command with parameters
        #

        elif len(arg_list) == 1:

            pgsql_node = arg_list[0]

            if self.output_format == 'table':

                print '--------------------------------------------------------'
                print '# NodeID / FQDN: ' + str(pgsql_node)
                print '--------------------------------------------------------'

            try:

                result = self.db.show_databases_without_backup_definitions(pgsql_node)

                colnames = ['PgSQL node','DBname']
                self.generate_output(result,colnames,["PgSQL node","DBname"],'databases_without_backup_definitions')

            except Exception as e:
                print '--------------------------------------------------------'
                self.processing_error('[ERROR]: ' + str(e) + '\n')
                return False

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        print


    # ############################################
    # Method do_show_snapshot_in_progress
    # ############################################

    def do_show_snapshots_in_progress(self,args):
        '''
        DESCRIPTION:

        This command shows all snapshot jobs in progress.

        COMMAND:
        show_snapshots_in_progress

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            try:
                result = self.db.show_snapshots_in_progress()

                colnames = [desc[0] for desc in result.description]
                self.generate_output(result,colnames,["Backup server","PgSQL node","DBname","AT time","Code"],'snapshots_in_progress')

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')

        #
        # Command with the wrong number of parameters
        #

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        print


    # ############################################
    # Method do_show_restores_in_progress
    # ############################################

    def do_show_restores_in_progress(self,args):
        '''
        DESCRIPTION:

        This command shows all restore jobs in progress.

        COMMAND:
        show_restores_in_progress

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            try:
                result = self.db.show_restores_in_progress()

                colnames = [desc[0] for desc in result.description]
                self.generate_output(result,colnames,["Backup server","Target PgSQL node","Target DBname","AT time"],'restores_in_progress')


            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')


        #
        # Command with the wrong number of parameters
        #

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        print


    # ############################################
    # Method do_update_backup_server
    # ############################################

    def do_update_backup_server(self,args):
        '''
        DESCRIPTION:
        This command updates the information of a backup server.

        COMMAND:
        update_backup_server [SrvID | FQDN]
                             [remarks]

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Default backup server
        #

        default_backup_server = self.get_default_backup_server()

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            ack = ''

            try:
                print '--------------------------------------------------------'
                backup_server = raw_input('# SrvID / FQDN [' + default_backup_server+ ']: ').strip()

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            try:

                if backup_server == '':
                    backup_server = default_backup_server

                if backup_server.isdigit():
                    backup_server_id = backup_server
                else:
                    backup_server_id = self.db.get_backup_server_id(backup_server)

            except Exception as e:
                print '--------------------------------------------------------'
                self.processing_error('[ERROR]: ' + str(e) + '\n')
                return False

            try:
                remarks_default = self.db.get_backup_server_def_value(backup_server_id,'remarks')

            except Exception as e:
                print '--------------------------------------------------------'
                self.processing_error('[ERROR]: Problems getting default values for parameters\n' + str(e) + '\n')
                return False

            try:
                remarks = raw_input('# Remarks [' + remarks_default + ']: ')
                print

                while ack != 'yes' and ack != 'no':
                    ack = raw_input('# Are all values to update correct (yes/no): ')

                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            if remarks == '':
                remarks = remarks_default

            if ack.lower() == 'yes':
                try:
                    self.db.update_backup_server(backup_server_id,remarks.strip())
                    print '[DONE] Backup server with SrvID: ' + str(backup_server_id) + ' updated.\n'

                except Exception as e:
                    self.processing_error('[ERROR]: Could not update this backup server\n' + str(e) + '\n')

            elif ack.lower() == 'no':
                print '[ABORTED] Command interrupted by the user.\n'

        #
        # Command with parameters
        #

        elif len(arg_list) == 2:

            backup_server = arg_list[0]

            try:

                if backup_server == '':
                    backup_server = default_backup_server

                if backup_server.isdigit():
                    backup_server_id = backup_server
                else:
                    backup_server_id = self.db.get_backup_server_id(backup_server)

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')
                return False

            try:
                remarks_default = self.db.get_backup_server_def_value(backup_server_id,'remarks')

            except Exception as e:
                self.processing_error('[ERROR]: Problems getting default values for parameters\n' + str(e) + '\n')
                return False

            remarks = arg_list[1]

            if remarks == '':
                remarks = remarks_default

            try:
                self.db.update_backup_server(backup_server_id,remarks.strip())
                print '[DONE] Backup server with SrvID: ' + str(backup_server_id) + ' updated.\n'

            except Exception as e:
                self.processing_error('[ERROR]: Could not update this backup server\n' + str(e) + '\n')

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        print


    # ############################################
    # Method do_update_pgsql_node
    # ############################################

    def do_update_pgsql_node(self,args):
        '''
        DESCRIPTION:
        This command updates the information of a PgSQL node.

        COMMAND:
        update_pgsql_node [NodeID | FQDN]
                          [pgport]
                          [admin_user]
                          [status]
                          [remarks]

        [NodeID | FQDN]:
        ----------------
        NodeID in PgBackMan or FQDN of the PgSQL node to update.

        [pgport]:
        ---------
        PostgreSQL port.

        [admin_user]:
        -------------
        PostgreSQL admin user.

        [Status]:
        ---------
        RUNNING: PostgreSQL node running and online
        DOWN: PostgreSQL node not online.

        [remarks]:
        ----------
        Remarks

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            ack = ''

            try:
                print '--------------------------------------------------------'
                pgsql_node = raw_input('# NodeID / FQDN []: ').strip()

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            try:
                if pgsql_node.isdigit():
                    pgsql_node_id = pgsql_node
                else:
                    pgsql_node_id = self.db.get_pgsql_node_id(pgsql_node)

            except Exception as e:
                print '--------------------------------------------------------'
                self.processing_error('[ERROR]: ' + str(e) + '\n')
                return False

            try:
                port_default = self.db.get_pgsql_node_def_value(pgsql_node_id,'pgport')
                admin_user_default = self.db.get_pgsql_node_def_value(pgsql_node_id,'admin_user')
                status_default = self.db.get_pgsql_node_def_value(pgsql_node_id,'status')
                remarks_default = self.db.get_pgsql_node_def_value(pgsql_node_id,'remarks')

            except Exception as e:
                print '--------------------------------------------------------'
                self.processing_error('[ERROR]: Problems getting default values for parameters\n' + str(e) + '\n')
                return False

            try:
                port = raw_input('# Port [' + port_default + ']: ')
                admin_user = raw_input('# Admin user [' + admin_user_default + ']: ')
                status = raw_input('# Status[' + status_default + ']: ')
                remarks = raw_input('# Remarks [' + remarks_default + ']: ')
                print

                while ack != 'yes' and ack != 'no':
                    ack = raw_input('# Are all values to update correct (yes/no): ')

                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            if port == '':
                port = port_default

            if admin_user == '':
                admin_user = admin_user_default

            if status == '':
                status = status_default

            if remarks == '':
                remarks = remarks_default

            if ack.lower() == 'yes':
                if self.check_port(port):
                    try:
                        self.db.update_pgsql_node(pgsql_node_id,port.strip(),admin_user.lower().strip(),status.upper().strip(),remarks.strip())
                        print '[DONE] PgSQL node with NodeID: ' + str(pgsql_node_id) + ' updated.\n'

                    except Exception as e:
                        self.processing_error('[ERROR]: Could not update this PgSQL node\n' + str(e) + '\n')

            elif ack.lower() == 'no':
                print '[ABORTED] Command interrupted by the user.\n'

        #
        # Command with parameters
        #

        elif len(arg_list) == 5:

            pgsql_node = arg_list[0]

            try:
                if pgsql_node.isdigit():
                    pgsql_node_id = pgsql_node
                else:
                    pgsql_node_id = self.db.get_pgsql_node_id(pgsql_node)

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')
                return False

            try:
                port_default = self.db.get_pgsql_node_def_value(pgsql_node_id,'pgport')
                admin_user_default = self.db.get_pgsql_node_def_value(pgsql_node_id,'admin_user')
                status_default = self.db.get_pgsql_node_def_value(pgsql_node_id,'status')
                remarks_default = self.db.get_pgsql_node_def_value(pgsql_node_id,'remarks')

            except Exception as e:
                self.processing_error('[ERROR]: Problems getting default values for parameters\n' + str(e) + '\n')
                return False

            port = arg_list[1]
            admin_user = arg_list[2]
            status = arg_list[3]
            remarks = arg_list[4]

            if port == '':
                port = port_default

            if admin_user == '':
                admin_user = admin_user_default

            if status == '':
                status = status_default

            if remarks == '':
                remarks = remarks_default

            if self.check_port(port):
                try:
                    self.db.update_pgsql_node(pgsql_node_id,port.strip(),admin_user.lower().strip(),status.upper().strip(),remarks.strip())
                    print '[DONE] PgSQL node with NodeID: ' + str(pgsql_node_id) + ' updated.\n'

                except Exception as e:
                    self.processing_error('[ERROR]: Could not update this PgSQL node\n' + str(e) + '\n')

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        print


    # ############################################
    # Method do_update_pgsql_node_config
    # ############################################

    def do_update_pgsql_node_config(self,args):
        '''
        DESCRIPTION:
        This command updates the default configuration parameters
        for a PgSQL node

        COMMAND:
        update_pgsql_node_config [NodeID / FQDN]
                                 [min_cron interval]
                                 [hours_cron interval]
                                 [daymonth_cron]
                                 [month_cron]
                                 [weekday_cron]
                                 [backup code]
                                 [retention period]
                                 [retention redundancy]
                                 [automatic deletion retention]
                                 [extra backup parameters]
                                 [extra restore parameters]
                                 [backup job status]
                                 [domain]
                                 [logs email]
                                 [admin user]
                                 [pgport]
                                 [pgnode backup dir]
                                 [pgnode crontab file]
                                 [pgnode status]

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            ack = ''

            try:
                print '--------------------------------------------------------'
                pgsql_node = raw_input('# NodeID / FQDN []: ').strip()
                print

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            try:
                if pgsql_node.isdigit():
                    pgsql_node_fqdn = self.db.get_pgsql_node_fqdn(pgsql_node)
                    pgsql_node_id = pgsql_node
                else:
                    pgsql_node_id = self.db.get_pgsql_node_id(pgsql_node)

            except Exception as e:
                print '--------------------------------------------------------'
                self.processing_error('[ERROR]: ' + str(e) + '\n')
                return False

            try:
                backup_minutes_interval_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_minutes_interval')
                backup_hours_interval_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_hours_interval')
                backup_weekday_cron_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_weekday_cron')
                backup_month_cron_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_month_cron')
                backup_day_month_cron_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_day_month_cron')

                backup_code_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_code')
                retention_period_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'retention_period')
                retention_redundancy_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'retention_redundancy')
                automatic_deletion_retention_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'automatic_deletion_retention')
                extra_backup_parameters_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'extra_backup_parameters')
                extra_restore_parameters_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'extra_restore_parameters')
                backup_job_status_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_job_status')

                domain_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'domain')
                logs_email_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'logs_email')
                admin_user_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'admin_user')
                pgport_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'pgport')

                pgnode_backup_partition_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'pgnode_backup_partition')
                pgnode_crontab_file_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'pgnode_crontab_file')
                pgsql_node_status_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'pgsql_node_status')

            except Exception as e:
                print '--------------------------------------------------------'
                self.processing_error('[ERROR]: Problems getting default values for parameters\n' + str(e) + '\n')
                return False

            try:
                backup_minutes_interval = raw_input('# Minutes cron interval [' + backup_minutes_interval_default + ']: ').strip()
                backup_hours_interval = raw_input('# Hours cron interval [' + backup_hours_interval_default + ']: ').strip()
                backup_day_month_cron = raw_input('# Day-month cron [' + backup_day_month_cron_default + ']: ').strip()
                backup_month_cron = raw_input('# Month cron [' + backup_month_cron_default + ']: ').strip()
                backup_weekday_cron = raw_input('# Weekday cron [' + backup_weekday_cron_default + ']: ').strip()
                print
                backup_code = raw_input('# Backup code [' + backup_code_default + ']: ').strip()
                retention_period = raw_input('# Retention period [' + retention_period_default + ']: ').strip()
                retention_redundancy = raw_input('# Retention redundancy [' + retention_redundancy_default + ']: ').strip()
                automatic_deletion_retention = raw_input('# Automatic deletion retention [' + automatic_deletion_retention_default + ']: ').strip()
                extra_backup_parameters = raw_input('# Extra backup parameters [' + extra_backup_parameters_default + ']: ').strip()
                extra_restore_parameters = raw_input('# Extra restore parameters [' + extra_restore_parameters_default + ']: ').strip()
                backup_job_status = raw_input('# Backup Job status [' + backup_job_status_default + ']: ').strip()
                print
                domain = raw_input('# Domain [' + domain_default + ']: ').strip()
                logs_email = raw_input('# Logs e-mail [' + logs_email_default + ']: ').strip()
                admin_user = raw_input('# PostgreSQL admin user [' + admin_user_default + ']: ').strip()
                pgport = raw_input('# Port [' + pgport_default + ']: ').strip()
                print
                pgnode_backup_partition = raw_input('# Backup directory [' + pgnode_backup_partition_default + ']: ').strip()
                pgnode_crontab_file = raw_input('# Crontab file [' + pgnode_crontab_file_default + ']: ').strip()
                pgsql_node_status = raw_input('# PgSQL node status [' + pgsql_node_status_default + ']: ').strip()
                print

                while ack != 'yes' and ack != 'no':
                    ack = raw_input('# Are all values to update correct (yes/no): ')

                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            if backup_minutes_interval != '':
                if not self.check_minutes_interval(backup_minutes_interval):
                    print '[WARNING]: Wrong minutes interval format, using default.'
                    backup_minutes_interval = backup_minutes_interval_default
            else:
                backup_minutes_interval = backup_minutes_interval_default

            if backup_hours_interval != '':
                if not self.check_hours_interval(backup_hours_interval):
                    print '[WARNING]: Wrong hours interval format, using default.'
                    backup_hours_interval = backup_hours_interval_default
            else:
                backup_hours_interval = backup_hours_interval_default

            if backup_weekday_cron == '':
                backup_weekday_cron = backup_weekday_cron_default

            if backup_month_cron == '':
                backup_month_cron = backup_month_cron_default

            if backup_day_month_cron == '':
                backup_day_month_cron = backup_day_month_cron_default

            if  backup_code != '':
                if backup_code.upper() not in ['CLUSTER','FULL','DATA','SCHEMA']:
                    print '[WARNING]: Wrong backup code, using default.'
                    backup_code = backup_code_default
            else:
                backup_code = backup_code_default

            if retention_period == '':
                retention_period = retention_period_default

            if retention_redundancy == '':
                retention_redundancy = retention_redundancy_default

            if automatic_deletion_retention == '':
                automatic_deletion_retention = automatic_deletion_retention_default

            if extra_backup_parameters == '':
                extra_backup_parameters = extra_backup_parameters_default

            if extra_restore_parameters == '':
                extra_restore_parameters = extra_restore_parameters_default

            if backup_job_status != '':
                if backup_job_status.upper() not in ['ACTIVE','STOPPED']:
                    print '[WARNING]: Wrong job status, using default.'
                    backup_job_status = backup_job_status_default
            else:
                backup_job_status = backup_job_status_default

            if domain == '':
                domain = domain_default

            if logs_email == '':
                logs_email = logs_email_default

            if admin_user == '':
                admin_user = admin_user_default

            if not pgport.isdigit() or pgport == '':
                pgport = pgport_default

            if pgnode_backup_partition == '':
                pgnode_backup_partition = pgnode_backup_partition_default

            if pgnode_crontab_file == '':
                pgnode_crontab_file = pgnode_crontab_file_default

            if pgsql_node_status != '':
                if pgsql_node_status.upper() not in ['RUNNING','STOPPED']:
                    print '[WARNING]: Wrong node status, using default.'
                    pgsql_node_status = pgsql_node_status_default
            else:
                pgsql_node_status = pgsql_node_status_default

            if ack.lower() == 'yes':
                try:
                    self.db.update_pgsql_node_config(pgsql_node_id,backup_minutes_interval.strip(),backup_hours_interval.strip(),backup_weekday_cron.strip(),
                                                     backup_month_cron.strip(),backup_day_month_cron.strip(),backup_code.strip().upper(),retention_period.strip(),
                                                     retention_redundancy.strip(),automatic_deletion_retention.strip(),extra_backup_parameters.strip(),
                                                     extra_restore_parameters.strip(),backup_job_status.strip().upper(),domain.strip(),logs_email.strip(),
                                                     admin_user.strip(),pgport,pgnode_backup_partition.strip(),pgnode_crontab_file.strip(),pgsql_node_status.strip().upper())

                    print '[DONE] Configuration parameters for NodeID: ' + str(pgsql_node_id) + ' updated.\n'

                except Exception as e:
                    self.processing_error('[ERROR]: Could not update the configuration for this PgSQL node \n' + str(e) + '\n')

            elif ack.lower() == 'no':
                print '[ABORTED] Command interrupted by the user.\n'

        #
        # Command with parameters
        #

        elif len(arg_list) == 20:

            pgsql_node = arg_list[0]

            try:
                if pgsql_node.isdigit():
                    pgsql_node_fqdn = self.db.get_pgsql_node_fqdn(pgsql_node)
                    pgsql_node_id = pgsql_node
                else:
                    pgsql_node_id = self.db.get_pgsql_node_id(pgsql_node)

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')
                return False

            try:
                backup_minutes_interval_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_minutes_interval')
                backup_hours_interval_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_hours_interval')
                backup_weekday_cron_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_weekday_cron')
                backup_month_cron_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_month_cron')
                backup_day_month_cron_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_day_month_cron')

                backup_code_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_code')
                retention_period_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'retention_period')
                retention_redundancy_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'retention_redundancy')
                automatic_deletion_retention_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'automatic_deletion_retention')
                extra_backup_parameters_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'extra_backup_parameters')
                extra_restore_parameters_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'extra_restore_parameters')
                backup_job_status_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'backup_job_status')

                domain_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'domain')
                logs_email_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'logs_email')
                admin_user_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'admin_user')
                pgport_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'pgport')

                pgnode_backup_partition_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'pgnode_backup_partition')
                pgnode_crontab_file_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'pgnode_crontab_file')
                pgsql_node_status_default = self.db.get_pgsql_node_config_value(pgsql_node_id,'pgsql_node_status')

            except Exception as e:
                self.processing_error('[ERROR]: Problems getting default values for parameters\n' + str(e) + '\n')
                return False

            backup_minutes_interval = arg_list[1]
            backup_hours_interval = arg_list[2]
            backup_day_month_cron = arg_list[3]
            backup_month_cron = arg_list[4]
            backup_weekday_cron = arg_list[5]
            backup_code = arg_list[6]
            retention_period = arg_list[7]
            retention_redundancy = arg_list[8]
            extra_backup_parameters = arg_list[9]
            extra_restore_parameters = arg_list[10]
            automatic_deletion_retention  = arg_list[11]
            backup_job_status = arg_list[12]
            domain = arg_list[13]
            logs_email = arg_list[14]
            admin_user = arg_list[15]
            pgport = arg_list[16]
            pgnode_backup_partition = arg_list[17]
            pgnode_crontab_file = arg_list[18]
            pgsql_node_status = arg_list[19]

            if backup_minutes_interval != '':
                if not self.check_minutes_interval(backup_minutes_interval):
                    print '[WARNING]: Wrong minutes interval format, using default.'
                    backup_minutes_interval = backup_minutes_interval_default
            else:
                backup_minutes_interval = backup_minutes_interval_default

            if backup_hours_interval == '':
                if not self.check_hours_interval(backup_hours_interval):
                    print '[WARNING]: Wrong hours interval format, using default.'
                    backup_hours_interval = backup_hours_interval_default
            else:
                backup_hours_interval = backup_hours_interval_default

            if backup_weekday_cron == '':
                backup_weekday_cron = backup_weekday_cron_default

            if backup_month_cron == '':
                backup_month_cron = backup_month_cron_default

            if backup_day_month_cron == '':
                backup_day_month_cron = backup_day_month_cron_default

            if  backup_code != '':
                if backup_code.upper() not in ['CLUSTER','FULL','DATA','SCHEMA']:
                    print '[WARNING]: Wrong backup code, using default.'
                    backup_code = backup_code_default
            else:
                backup_code = backup_code_default

            if retention_period == '':
                retention_period = retention_period_default

            if retention_redundancy == '':
                retention_redundancy = retention_redundancy_default

            if automatic_deletion_retention == '':
                automatic_deletion_retention = automatic_deletion_retention_default

            if extra_backup_parameters == '':
                extra_backup_parameters = extra_backup_parameters_default

            if extra_restore_parameters == '':
                extra_restore_parameters = extra_restore_parameters_default

            if backup_job_status == '':
                if backup_job_status.upper() not in ['ACTIVE','STOPPED']:
                    print '[WARNING]: Wrong job status, using default.'
                    backup_job_status = backup_job_status_default
            else:
                backup_job_status = backup_job_status_default

            if domain == '':
                domain = domain_default

            if logs_email == '':
                logs_email = logs_email_default

            if admin_user == '':
                admin_user = admin_user_default

            if not pgport.isdigit() or pgport == '':
                pgport = pgport_default

            if pgnode_backup_partition == '':
                pgnode_backup_partition = pgnode_backup_partition_default

            if pgnode_crontab_file == '':
                pgnode_crontab_file = pgnode_crontab_file_default

            if pgsql_node_status == '':
                if pgsql_node_status.upper() not in ['RUNNING','STOPPED']:
                    print '[WARNING]: Wrong node status, using default.'
                    pgsql_node_status = pgsql_node_status_default
            else:
                pgsql_node_status = pgsql_node_status_default

            try:
                self.db.update_pgsql_node_config(pgsql_node_id,backup_minutes_interval.strip(),backup_hours_interval.strip(),backup_weekday_cron.strip(),
                                                 backup_month_cron.strip(),backup_day_month_cron.strip(),backup_code.strip().upper(),retention_period.strip(),
                                                 retention_redundancy.strip(),automatic_deletion_retention.strip(),extra_backup_parameters.strip(),
                                                 extra_restore_parameters.strip(),backup_job_status.strip().upper(),domain.strip(),logs_email.strip(),
                                                 admin_user.strip(),pgport,pgnode_backup_partition.strip(),pgnode_crontab_file.strip(),pgsql_node_status.strip().upper())

                print '[DONE] Configuration parameters for NodeID: ' + str(pgsql_node_id) + ' updated.\n'

            except Exception as e:
                self.processing_error('[ERROR]: Could not update the configuration for this PgSQL node \n' + str(e) + '\n')

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        print


    # ############################################
    # Method do_update_backup_server_config
    # ############################################

    def do_update_backup_server_config(self,args):
        '''
        DESCRIPTION:
        This command updates the default configuration parameters
        for a backup server

        COMMAND:
        update_backup_server_config [SrvID / FQDN]
                                    [pgbackman_dump_command]
                                    [pgbackman_restore_command]
                                    [admin_user]
                                    [domain]
                                    [root_backup_dir]

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Default backup server
        #

        default_backup_server = self.get_default_backup_server()

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            ack = ''

            try:
                print '--------------------------------------------------------'
                backup_server = raw_input('# SrvID / FQDN [' + default_backup_server + ']: ').strip()
                print

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            try:
                if backup_server == '':
                    backup_server = default_backup_server

                if backup_server.isdigit():
                    backup_server_fqdn = self.db.get_backup_server_fqdn(backup_server)
                    backup_server_id = backup_server
                else:
                    backup_server_id = self.db.get_backup_server_id(backup_server)

            except Exception as e:
                print '--------------------------------------------------------'
                self.processing_error('[ERROR]: ' + str(e) + '\n')
                return False

            try:
                pgbackman_dump_command_default    = self.db.get_backup_server_config_value(backup_server_id,'pgbackman_dump')
                pgbackman_restore_command_default = self.db.get_backup_server_config_value(backup_server_id,'pgbackman_restore')
                admin_user_default                = self.db.get_backup_server_config_value(backup_server_id,'admin_user')
                domain_default                    = self.db.get_backup_server_config_value(backup_server_id,'domain')
                root_backup_partition_default     = self.db.get_backup_server_config_value(backup_server_id,'root_backup_partition')

            except Exception as e:
                print '--------------------------------------------------------'
                self.processing_error('[ERROR]: Problems getting default values for parameters\n' + str(e) + '\n')
                return False

            try:
                pgbackman_dump_command    = raw_input('# pgbackman_dump command [' + pgbackman_dump_command_default + ']: ').strip()
                pgbackman_restore_command = raw_input('# pgbackman_restore command [' + pgbackman_restore_command_default + ']: ').strip()
                admin_user                = raw_input('# Admin user [' + admin_user_default + ']: ').strip()
                domain                    = raw_input('# Domain [' + domain_default + ']: ').strip()
                root_backup_partition     = raw_input('# Main backup dir [' + root_backup_partition_default + ']: ').strip()
                print

                while ack != 'yes' and ack != 'no':
                    ack = raw_input('# Are all values to update correct (yes/no): ')

                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            if pgbackman_dump_command == '':
                pgbackman_dump_command = pgbackman_dump_command_default

            if pgbackman_restore_command == '':
                pgbackman_restore_command = pgbackman_restore_command_default

            if admin_user == '':
                admin_user = admin_user_default

            if domain == '':
                domain = domain_default

            if root_backup_partition == '':
                root_backup_partition = root_backup_partition_default


            if ack.lower() == 'yes':
                try:
                    self.db.update_backup_server_config(backup_server_id,
                                                        pgbackman_dump_command,
                                                        pgbackman_restore_command,
                                                        admin_user,
                                                        domain,
                                                        root_backup_partition)

                    print '[DONE] Configuration parameters for SrvID: ' + str(backup_server_id) + ' updated.\n'

                except Exception as e:
                    self.processing_error('[ERROR]: Could not update the configuration for this Backup server \n' + str(e) + '\n')

            elif ack.lower() == 'no':
                print '[ABORTED] Command interrupted by the user.\n'

        #
        # Command with parameters
        #

        elif len(arg_list) == 6:

            backup_server = arg_list[0]
            backup_server_id = ''

            try:
                if backup_server == '':
                    backup_server = default_backup_server

                if backup_server.isdigit():
                    backup_server_fqdn = self.db.get_backup_server_fqdn(backup_server)
                    backup_server_id = backup_server
                else:
                    backup_server_id = self.db.get_backup_server_id(backup_server)

            except Exception as e:
                self.processing_error('[ERROR]: ' + str(e) + '\n')
                return False

            try:
                pgbackman_dump_command_default    = self.db.get_backup_server_config_value(backup_server_id,'pgbackman_dump')
                pgbackman_restore_command_default = self.db.get_backup_server_config_value(backup_server_id,'pgbackman_restore')
                admin_user_default                = self.db.get_backup_server_config_value(backup_server_id,'admin_user')
                domain_default                    = self.db.get_backup_server_config_value(backup_server_id,'domain')
                root_backup_partition_default     = self.db.get_backup_server_config_value(backup_server_id,'root_backup_partition')

            except Exception as e:
                self.processing_error('[ERROR]: Problems getting default values for parameters\n' + str(e) + '\n')
                return False

            pgbackman_dump_command    = arg_list[1]
            pgbackman_restore_command = arg_list[2]
            admin_user                = arg_list[3]
            domain                    = arg_list[4]
            root_backup_partition     = arg_list[5]

            if pgbackman_dump_command == '':
                pgbackman_dump_command = pgbackman_dump_command_default

            if pgbackman_restore_command == '':
                pgbackman_restore_command = pgbackman_restore_command_default

            if admin_user == '':
                admin_user = admin_user_default

            if domain == '':
                domain = domain_default

            if root_backup_partition == '':
                root_backup_partition = root_backup_partition_default

            try:
                self.db.update_backup_server_config(backup_server_id,
                                                    pgbackman_dump_command,
                                                    pgbackman_restore_command,
                                                    admin_user,
                                                    domain,
                                                    root_backup_partition)

                print '[DONE] Configuration parameters for SrvID: ' + str(backup_server_id) + ' updated.\n'

            except Exception as e:
                self.processing_error('[ERROR]: Could not update the configuration for this Backup server \n' + str(e) + '\n')

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        print

    # ############################################
    # Method do_register_backup_server_pg_bin_dir
    # ############################################

    def do_register_backup_server_pg_bin_dir(self,args):
        '''
        DESCRIPTION:
        This command configures the binary path for a given version of postgres
        on the specificed backup server

        COMMAND:
        register_backup_server_pg_bin_dir [SrvID / FQDN]
                                          [postgres_version]
                                          [bin_dir]

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Check argument count
        #

        if len(arg_list) > 0 and len(arg_list) != 3:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        #
        # Default backup server
        #

        default_backup_server = self.get_default_backup_server()

        postgres_version = ''
        bin_dir          = None

        #
        # Get the backup server id and postgres version being configured
        #

        if len(arg_list) == 0:
            # When no arguements are provided...

            try:
                print '--------------------------------------------------------'
                backup_server = raw_input('# SrvID / FQDN [' + default_backup_server + ']: ').strip()

                while not re.match( '\d{2,}|9[._][1-6]', postgres_version ):
                    postgres_version = raw_input('# Postgres Version: ').strip()
                    if not re.match( '\d{2,}|9[._][1-6]', postgres_version ):
                        print '"' + postgres_version + '" does not appear to be a valid postgres version'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

        else:
            # When arguments are provided

            backup_server    = arg_list[0]
            postgres_version = arg_list[1]

        #
        # Normalize backup server to numeric id
        #

        try:
            if backup_server == '':
                backup_server = default_backup_server

            if not backup_server.isdigit():
                backup_server = self.db.get_backup_server_id(backup_server)

        except Exception as e:
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Use the version to derive the defaults for the other values
        #

        bin_dir_default = '/usr/pgsql-' + str(postgres_version).replace('_','.') + '/bin'
        description     = 'postgreSQL ' + str(postgres_version).replace('_','.') + ' bin directory'

        #
        # Get the binary path parameter
        #

        if len(arg_list) == 0:
            # When no arguements are provided...

            ack = ''

            try:
                bin_dir     = raw_input('# Postgres binary directory: [' + bin_dir_default + ']: ').strip()
                print

                while ack != 'yes' and ack != 'no':
                    ack = raw_input('# Are all values to update correct (yes/no): ')

                print '--------------------------------------------------------'

                if ack.lower() == 'no':
                    print '[ABORTED] Command interrupted by the user.\n'
                    return False

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

        else:
            # When no arguements are provided
            bin_dir     = arg_list[2]

        # change any .s in the version to _s to because that's what the backend function expects
        postgres_version = postgres_version.replace('.','_')

        if bin_dir == '':
            bin_dir = bin_dir_default

        try:
            self.db.register_backup_server_pg_bin_dir(backup_server,
                                                      postgres_version,
                                                      bin_dir,
                                                      description)

            print '[DONE] Configured postgres ' + str(postgres_version) + ' for SrvID: ' + str(backup_server) + '.\n'

        except Exception as e:
            self.processing_error('[ERROR]: Could not update the configuration for this Backup server \n' + str(e) + '\n')

    # ############################################
    # Method do_update_backup_server_pg_bin_dir
    # ############################################

    def do_update_backup_server_pg_bin_dir(self,args):
        '''
        DESCRIPTION:
        This command updates the configrued binary path for a given version of postgres
        on the specificed backup server

        COMMAND:
        update_backup_server_pg_bin_dir [SrvID / FQDN]
                                        [postgres_version]
                                        [bin_dir]

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Check argument count
        #

        if len(arg_list) > 0 and len(arg_list) != 3:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        #
        # Default backup server
        #

        default_backup_server = self.get_default_backup_server()

        #
        # Get the backup server and postgres version being edited
        #

        postgres_version = ''
        bin_dir          = None
        bin_dir_default  = None

        if len(arg_list) == 0:
            # When no arguements are provided...

            try:
                print '--------------------------------------------------------'
                backup_server = raw_input('# SrvID / FQDN [' + default_backup_server + ']: ').strip()

                while not re.match( '\d{2,}|9[._][1-6]', postgres_version ):
                    postgres_version = raw_input('# Postgres Version: ').strip()
                    if not re.match( '\d{2,}|9[._][1-6]', postgres_version ):
                        print '"' + postgres_version + '" does not appear to be a valid postgres version'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

        else:
            # When arguments are provided

            backup_server    = arg_list[0]
            postgres_version = arg_list[1]

        #
        # Normalize backup server to numeric id
        #

        try:
            if backup_server == '':
                backup_server = default_backup_server

            if not backup_server.isdigit():
                backup_server = self.db.get_backup_server_id(backup_server)

        except Exception as e:
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Fetch this server's current setting to use as the default
        #

        postgres_version = postgres_version.replace('.','_')
        version_bin_dir_label = 'pgsql_bin_' + str(postgres_version)

        try:
            bin_dir_default = self.db.get_backup_server_config_value(backup_server,version_bin_dir_label)

        except Exception as e:
            self.processing_error('[ERROR]: Problems getting default values for parameters\n' + str(e) + '\n')
            return False

        #
        # Get the new binary path
        #

        if len(arg_list) == 0:
            # When no arguements are provided...

            ack = ''

            try:
                bin_dir = raw_input('# Postgres binary directory: [' + bin_dir_default + ']: ').strip()
                print

                while ack != 'yes' and ack != 'no':
                    ack = raw_input('# Are all values to update correct (yes/no): ')

                print '--------------------------------------------------------'

                if ack.lower() == 'no':
                    print '[ABORTED] Command interrupted by the user.\n'
                    return False

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

        else:
            # When no arguements are provided
            bin_dir = arg_list[2]

        if bin_dir == '':
            bin_dir = bin_dir_default

        try:
            self.db.update_backup_server_pg_bin_dir(backup_server,
                                                    postgres_version,
                                                    bin_dir)

            print '[DONE] Binary directory for postgres ' + str(postgres_version) + ' for SrvID: ' + str(backup_server) + ' updated.\n'

        except Exception as e:
            self.processing_error('[ERROR]: Could not update the configuration for this Backup server \n' + str(e) + '\n')

    # ############################################
    # Method do_delete_backup_server_pg_bin_dir
    # ############################################

    def do_delete_backup_server_pg_bin_dir(self,args):
        '''
        DESCRIPTION:
        This command drops support for a given version of postgres on the
        specificed backup server

        COMMAND:
        delete_backup_server_pg_bin_dir [SrvID / FQDN]
                                        [postgres_version]

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Check argument count
        #

        if len(arg_list) > 0 and len(arg_list) != 2:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        #
        # Default backup server
        #

        default_backup_server = self.get_default_backup_server()

        #
        # Get the backup server and postgres version being edited
        #

        postgres_version = ''

        if len(arg_list) == 0:
            # When no arguements are provided...

            try:
                ack = ''

                print '--------------------------------------------------------'
                backup_server = raw_input('# SrvID / FQDN [' + default_backup_server + ']: ').strip()

                while not re.match( '\d{2,}|9[._][1-6]', postgres_version ):
                    postgres_version = raw_input('# Postgres Version: ').strip()
                    if not re.match( '\d{2,}|9[._][1-6]', postgres_version ):
                        print '"' + postgres_version + '" does not appear to be a valid postgres version'

                while ack != 'yes' and ack != 'no':
                    ack = raw_input('# Are you sure you want to drop support for this version of postgres (yes/no): ')

                print '--------------------------------------------------------'

                if ack.lower() == 'no':
                    print '[ABORTED] Command interrupted by the user.\n'
                    return False

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

        else:
            # When arguments are provided

            backup_server    = arg_list[0]
            postgres_version = arg_list[1]

        #
        # Normalize backup server to numeric id
        #

        try:
            if backup_server == '':
                backup_server = default_backup_server

            if not backup_server.isdigit():
                backup_server = self.db.get_backup_server_id(backup_server)

        except Exception as e:
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        postgres_version = postgres_version.replace('.','_')
        version_bin_dir_label = 'pgsql_bin_' + str(postgres_version)

        try:
            self.db.delete_backup_server_pg_bin_dir(backup_server,
                                                    postgres_version)

            print '[DONE] Dropped postgres ' + str(postgres_version) + ' for SrvID: ' + str(backup_server) + '.\n'

        except Exception as e:
            self.processing_error('[ERROR]: Could not update the configuration for this Backup server \n' + str(e) + '\n')

    # ########################################################
    # Method do_show_backup_server_default_configured_versions
    # ########################################################

    def do_show_backup_server_default_configured_versions(self,args):
        '''
        DESCRIPTION:
        This command lists the versions of postgres configured on backup
        servers by default

        COMMAND:
        do_show_backup_server_configured_versions

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Check argument count
        #

        if len(arg_list) > 0:
            self.processing_error('\n[ERROR] - This command does not accept parameters.\n          Type help or ? to list commands\n')

        try:
            result = self.db.show_backup_server_default_configured_versions()
            self.generate_output(result,['Version','Binary Path'],['parameter','value'],'backup_server_default_postgres_versions')

        except Exception as e:
            self.processing_error('[ERROR]: ' + str(e) + '\n')

    # ###################################################
    # Method do_register_backup_server_default_pg_bin_dir
    # ###################################################

    def do_register_backup_server_default_pg_bin_dir(self,args):
        '''
        DESCRIPTION:
        This command configures the default binary directory to use for a given
        version of postgres

        COMMAND:
        register_backup_server_default_pg_bin_dir [postgres_version]
                                                  [bin_dir]

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Check argument count
        #

        if len(arg_list) > 0 and len(arg_list) != 2:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        postgres_version = ''
        bin_dir          = None

        #
        # Get the postgres version being configured
        #

        if len(arg_list) == 0:
            # When no arguements are provided...

            try:
                print '--------------------------------------------------------'

                while not re.match( '\d{2,}|9[._][1-6]', postgres_version ):
                    postgres_version = raw_input('# Postgres Version: ').strip()
                    if not re.match( '\d{2,}|9[._][1-6]', postgres_version ):
                        print '"' + postgres_version + '" does not appear to be a valid postgres version'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

        else:
            # When arguments are provided

            postgres_version = arg_list[0]

        #
        # Use the version to derive the defaults for the other values
        #

        bin_dir_default = '/usr/pgsql-' + str(postgres_version).replace('_','.') + '/bin'
        description     = 'postgreSQL ' + str(postgres_version).replace('_','.') + ' bin directory'

        #
        # Get the binary directory parameter
        #

        if len(arg_list) == 0:
            # When no arguements are provided...

            ack = ''

            try:
                bin_dir     = raw_input('# Postgres binary directory: [' + bin_dir_default + ']: ').strip()
                print

                while ack != 'yes' and ack != 'no':
                    ack = raw_input('# Are all values to update correct (yes/no): ')

                print '--------------------------------------------------------'

                if ack.lower() == 'no':
                    print '[ABORTED] Command interrupted by the user.\n'
                    return False

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

        else:
            # When no arguements are provided
            bin_dir     = arg_list[1]

        # change any .s in the version to _s to because that's what the backend function expects
        postgres_version = postgres_version.replace('.','_')

        if bin_dir == '':
            bin_dir = bin_dir_default

        try:
            self.db.register_backup_server_default_pg_bin_dir(postgres_version,
                                                              bin_dir,
                                                              description)

            print '[DONE] Configured default binary directory for postgre ' + str(postgres_version) + '.\n'

        except Exception as e:
            self.processing_error('[ERROR]: Could not update the default backup server configuration \n' + str(e) + '\n')


    # #################################################
    # Method do_update_backup_server_default_pg_bin_dir
    # #################################################

    def do_update_backup_server_default_pg_bin_dir(self,args):
        '''
        DESCRIPTION:
        This command updates the default binary directory to use for a given
        version of postgres.

        COMMAND:
        update_backup_server_default_pg_bin_dir [postgres_version]
                                                [bin_dir]

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Check argument count
        #

        if len(arg_list) > 0 and len(arg_list) != 2:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        #
        # Get the postgres version being edited
        #

        postgres_version = ''
        bin_dir          = None
        bin_dir_default  = None

        if len(arg_list) == 0:
            # When no arguements are provided...

            try:
                print '--------------------------------------------------------'

                while not re.match( '\d{2,}|9[._][1-6]', postgres_version ):
                    postgres_version = raw_input('# Postgres Version: ').strip()
                    if not re.match( '\d{2,}|9[._][1-6]', postgres_version ):
                        print '"' + postgres_version + '" does not appear to be a valid postgres version'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

        else:
            # When arguments are provided

            postgres_version = arg_list[0]

        #
        # Fetch the current default
        #

        postgres_version = postgres_version.replace('.','_')
        version_bin_dir_label = 'pgsql_bin_' + str(postgres_version)
        bin_dir_default = '/usr/pgsql-' + str(postgres_version).replace('_','.') + '/bin'

        #
        # Get the new binary path
        #

        if len(arg_list) == 0:
            # When no arguements are provided...

            ack = ''

            try:
                bin_dir = raw_input('# Postgres binary directory: [' + bin_dir_default + ']: ').strip()
                print

                while ack != 'yes' and ack != 'no':
                    ack = raw_input('# Are all values to update correct (yes/no): ')

                print '--------------------------------------------------------'

                if ack.lower() == 'no':
                    print '[ABORTED] Command interrupted by the user.\n'
                    return False

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

        else:
            # When no arguements are provided
            bin_dir = arg_list[1]

        if bin_dir == '':
            bin_dir = bin_dir_default

        try:
            self.db.update_backup_server_default_pg_bin_dir(postgres_version,
                                                            bin_dir)

            print '[DONE] Updated default binary directory for postgres version ' + str(postgres_version) + '.\n'

        except Exception as e:
            self.processing_error('[ERROR]: Could not update the default backup server configuration \n' + str(e) + '\n')

    # #################################################
    # Method do_delete_backup_server_default_pg_bin_dir
    # #################################################

    def do_delete_backup_server_default_pg_bin_dir(self,args):
        '''
        DESCRIPTION:
        This command drops support for the given version of postgres from the
        defaults

        COMMAND:
        delete_backup_server_default_pg_bin_dir [postgres_version]

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Check argument count
        #

        if len(arg_list) > 0 and len(arg_list) != 1:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        #
        # Get the backup server and postgres version being edited
        #

        postgres_version = ''

        if len(arg_list) == 0:
            # When no arguements are provided...

            try:
                ack = ''

                print '--------------------------------------------------------'

                while not re.match( '\d{2,}|9[._][1-6]', postgres_version ):
                    postgres_version = raw_input('# Postgres Version: ').strip()
                    if not re.match( '\d{2,}|9[._][1-6]', postgres_version ):
                        print '"' + postgres_version + '" does not appear to be a valid postgres version'

                while ack != 'yes' and ack != 'no':
                    ack = raw_input('# Are you sure you want to drop support for this version of postgres (yes/no): ')

                print '--------------------------------------------------------'

                if ack.lower() == 'no':
                    print '[ABORTED] Command interrupted by the user.\n'
                    return False

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

        else:
            # When arguments are provided

            postgres_version = arg_list[0]

        postgres_version = postgres_version.replace('.','_')

        try:
            self.db.delete_backup_server_default_pg_bin_dir(postgres_version)

            print '[DONE] Dropped postgres version ' + str(postgres_version) + ' support by default.\n'

        except Exception as e:
            self.processing_error('[ERROR]: Could not update the default backup server configuration \n' + str(e) + '\n')


    # ############################################
    # Method do_update_backup_definition
    # ############################################

    def do_update_backup_definition(self,args):
        '''
        DESCRIPTION:
        This command updates the information of a backup definition

        COMMAND:
        update_backup_definition [DefID]
                                 [min_cron]
                                 [hour_cron]
                                 [day-month_cron]
                                 [month_cron]
                                 [weekday_cron]
                                 [retention period]
                                 [retention redundancy]
                                 [extra backup parameters]
                                 [job status]
                                 [remarks]

        [DefID]:
        --------
        Backup definition ID to update.

        [*cron]:
        --------
        Schedule definition using the cron expression. Check
        http://en.wikipedia.org/wiki/Cron#CRON_expression for more
        information.

        [retention period]:
        -------------------
        Time interval, e.g. 2 hours, 3 days, 1 week, 1 month, 2 years, ...

        [retention redundancy]:
        -----------------------
        Integer: 1,2,3, .... Minimun number of backups to keep in the catalog
        regardless of the retention period used.

        [extra backup parameters]:
        ---------------
        Extra parameters that can be used with pg_dump / pg_dumpall

        [job status]:
        -------------
        ACTIVE: Backup job activated and in production.
        STOPPED: Backup job stopped.

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            ack = ''

            print '--------------------------------------------------------'

            try:
                def_id = raw_input('# DefID []: ')

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n',e,'\n'
                return False

            if def_id.isdigit():

                try:
                    minutes_cron_default = self.db.get_backup_definition_def_value(def_id,'minutes_cron')
                    hours_cron_default = self.db.get_backup_definition_def_value(def_id,'hours_cron')
                    weekday_cron_default = self.db.get_backup_definition_def_value(def_id,'weekday_cron')
                    month_cron_default = self.db.get_backup_definition_def_value(def_id,'month_cron')
                    day_month_cron_default = self.db.get_backup_definition_def_value(def_id,'day_month_cron')

                    retention_period_default = self.db.get_backup_definition_def_value(def_id,'retention_period')
                    retention_redundancy_default = self.db.get_backup_definition_def_value(def_id,'retention_redundancy')
                    extra_backup_parameters_default = self.db.get_backup_definition_def_value(def_id,'extra_backup_parameters')
                    job_status_default = self.db.get_backup_definition_def_value(def_id,'job_status')
                    remarks_default = self.db.get_backup_definition_def_value(def_id,'remarks')

                except Exception as e:
                    print '--------------------------------------------------------'
                    self.processing_error('[ERROR]: Problems getting default values for parameters\n' + str(e) + '\n')
                    return False
            else:
                self.processing_error('[ERROR]: DefID has to be a digit\n')
                return False

            try:
                minutes_cron = raw_input('# Minutes cron [' + str(minutes_cron_default) + ']: ')
                hours_cron = raw_input('# Hours cron [' + str(hours_cron_default) + ']: ')
                day_month_cron = raw_input('# Day-month cron [' + str(day_month_cron_default) + ']: ')
                month_cron = raw_input('# Month cron [' + str(month_cron_default) + ']: ')
                weekday_cron = raw_input('# Weekday cron [' + str(weekday_cron_default) + ']: ')
                retention_period = raw_input('# Retention period [' + str(retention_period_default) + ']: ')
                retention_redundancy = raw_input('# Retention redundancy [' + str(retention_redundancy_default) + ']: ')
                extra_backup_parameters = raw_input('# Extra backup parameters [' + str(extra_backup_parameters_default) + ']: ')
                job_status = raw_input('# Job status [' + str(job_status_default) + ']: ')
                remarks = raw_input('# Remarks [' + str(remarks_default) + ']: ')
                print

                while ack != 'yes' and ack != 'no':
                    ack = raw_input('# Are all values to update correct (yes/no): ')

                print '--------------------------------------------------------'

            except Exception as e:
                print '--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n',e,'\n'
                return False

            if minutes_cron == '':
                minutes_cron = minutes_cron_default

            if hours_cron == '':
                hours_cron = hours_cron_default

            if weekday_cron == '':
                weekday_cron = weekday_cron_default

            if month_cron == '':
                month_cron = month_cron_default

            if day_month_cron == '':
                day_month_cron = day_month_cron_default

            if retention_period == '':
                retention_period = retention_period_default

            if retention_redundancy == '':
                retention_redundancy = retention_redundancy_default

            if extra_backup_parameters == '':
                extra_backup_parameters = extra_backup_parameters_default

            if job_status == '':
                job_status = job_status_default

            if remarks == '':
                remarks = remarks_default

            if ack.lower() == 'yes':
                try:
                    self.db.update_backup_definition(def_id,minutes_cron,hours_cron,day_month_cron,month_cron,weekday_cron,retention_period,
                                                     retention_redundancy,extra_backup_parameters,job_status.upper(),remarks)

                    print '[DONE] Backup definition DefID: ' + str(def_id) + ' updated.\n'

                except Exception as e:
                    self.processing_error('[ERROR]: Could not update this Backup definition\n' + str(e) + '\n')

            elif ack.lower() == 'no':
                print '[ABORTED] Command interrupted by the user.\n'

        #
        # Command with parameters
        #

        elif len(arg_list) == 11:

            def_id = arg_list[0]

            if def_id.isdigit():

                try:
                    minutes_cron_default = self.db.get_backup_definition_def_value(def_id,'minutes_cron')
                    hours_cron_default = self.db.get_backup_definition_def_value(def_id,'hours_cron')
                    weekday_cron_default = self.db.get_backup_definition_def_value(def_id,'weekday_cron')
                    month_cron_default = self.db.get_backup_definition_def_value(def_id,'month_cron')
                    day_month_cron_default = self.db.get_backup_definition_def_value(def_id,'day_month_cron')

                    retention_period_default = self.db.get_backup_definition_def_value(def_id,'retention_period')
                    retention_redundancy_default = self.db.get_backup_definition_def_value(def_id,'retention_redundancy')
                    extra_backup_parameters_default = self.db.get_backup_definition_def_value(def_id,'extra_backup_parameters')
                    job_status_default = self.db.get_backup_definition_def_value(def_id,'job_status')
                    remarks_default = self.db.get_backup_definition_def_value(def_id,'remarks')

                except Exception as e:
                    self.processing_error('[ERROR]: Problems getting default values for parameters\n' + str(e) + '\n')
                    return False

            else:
                self.processing_error('[ERROR]: DefID has to be a digit.\n')
                return False

            minutes_cron = arg_list[1]
            hours_cron = arg_list[2]
            day_month_cron = arg_list[3]
            month_cron = arg_list[4]
            weekday_cron = arg_list[5]
            retention_period = arg_list[6]
            retention_redundancy = arg_list[7]
            extra_backup_parameters = arg_list[8]
            job_status = arg_list[9]
            remarks = arg_list[10]

            if minutes_cron == '':
                minutes_cron = minutes_cron_default

            if hours_cron == '':
                hours_cron = hours_cron_default

            if weekday_cron == '':
                weekday_cron = weekday_cron_default

            if month_cron == '':
                month_cron = month_cron_default

            if day_month_cron == '':
                day_month_cron = day_month_cron_default

            if retention_period == '':
                retention_period = retention_period_default

            if retention_redundancy == '':
                retention_redundancy = retention_redundancy_default

            if extra_backup_parameters == '':
                extra_backup_parameters = extra_backup_parameters_default

            if job_status == '':
                job_status = job_status_default

            if remarks == '':
                remarks = remarks_default

            try:
                self.db.update_backup_definition(def_id,minutes_cron,hours_cron,weekday_cron,month_cron,day_month_cron,retention_period,
                                                 retention_redundancy,extra_backup_parameters,job_status.upper(),remarks)

                print '[DONE] Backup definition DefID: ' + str(def_id) + ' updated.\n'

            except Exception as e:
                self.processing_error('[ERROR]: Could not update this Backup definition\n' + str(e) + '\n')

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        print

    # ############################################
    # Method do_set
    # ############################################

    def do_set(self,args):
        '''
        DESCRIPTION:

        This command can be used to change the value of some
        internal parameters used to configurate the behavior
        of PgBackMan

        COMMAND:
        set [parameter = value]

        [parameter = value]
        -------------------
        * output_format = [TABLE | JSON | CSV]

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        if len(arg_list) == 0:

            print '--------------------------------------------------------'

            try:
                input = raw_input('# Parameter=value: ')

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n',e,'\n'
                return False

            try:
                parameter, value = input.strip().replace(' ', '').split('=')

            except Exception as e:
                print '--------------------------------------------------------'
                self.processing_error('[ERROR]: The format used is not correct')
                return False

            if parameter == 'output_format':

                if value == '':
                    value = 'table'

                if value.lower() not in ['table', 'csv', 'json']:
                    self.processing_error('[ERROR]: Output format [' + value.lower() + '] is not a valid value\n')
                    return False

                try:
                    self.output_format = value.lower()

                    print '[DONE] Output format changed to [' + self.output_format + ']'

                except Exception as e:
                    print '--------------------------------------------------------'
                    self.processing_error('[ERROR]: ' + str(e) + '\n')

            else:
                self.processing_error('[ERROR]: Parameter [' + parameter.lower() + '] is not a valid parameter\n')

        elif len(arg_list) == 1:

            input = arg_list[0]

            try:
                parameter, value = input.strip().replace(' ', '').split('=')

            except Exception as e:
                print '--------------------------------------------------------'
                self.processing_error('[ERROR]: The format used is not correct')
                return False

            if parameter == 'output_format':

                if value == '':
                    value = 'table'

                if value.lower() not in ['table', 'csv', 'json']:
                    self.processing_error('[ERROR]: Output format [' + value.lower() + '] is not a valid value\n')
                    return False

                try:
                    self.output_format = value.lower()

                    print '[DONE] Output format changed to [' + self.output_format + ']'

                except Exception as e:
                    print '--------------------------------------------------------'
                    self.processing_error('[ERROR]: ' + str(e) + '\n')

            else:
                self.processing_error('[ERROR]: Parameter [' + parameter.lower() + '] is not a valid parameter\n')

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or \? to list commands\n')

        print


    # ############################################
    # Method do_move_backup_definition
    # ############################################

    def do_move_backup_definition(self,args):
        '''DESCRIPTION:

        This command moves backup definitions between backup servers
        for a particular combination of search values.

        COMMAND:
        move_backup_definition [From SrvID|FQDN]
                               [To SrvID|FQDN]
                               [NodeID|FQDN]
                               [DBname]
                               [DefID]


        [From SrvID | FQDN]:
        -------------------
        SrvID in PgBackMan or FQDN of the backup server running the
        backup jobs that will be move to another backup server.

        [To SrvID | FQDN]:
        -------------------
        SrvID in PgBackMan or FQDN of the backup server where we will
        move the backup jobs.

        [NodeID | FQDN]:
        ----------------
        NodeID in PgBackMan or FQDN of the PgSQL node where we take
        the backup jobs we want to move.

        One can use 'all' or '*' with this parameter.

        [Dbname]:
        ---------
        Database name in the backup jobs we want to move.

        One can use 'all' or '*' with this parameter.

        [DefID]:
        --------
        Backup definition ID we want to move.

        '''

        try:
            arg_list = shlex.split(args)

        except ValueError as e:
            print '--------------------------------------------------------'
            self.processing_error('[ERROR]: ' + str(e) + '\n')
            return False

        #
        # Default backup server
        #

        default_backup_server = self.get_default_backup_server()

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            ack = ''

            try:
                print '--------------------------------------------------------'
                from_server_id = raw_input('# From backup server SrvID / FQDN [' + default_backup_server + ']: ')
                to_server_id = raw_input('# To Backup server SrvID / FQDN [' + default_backup_server + ']: ')
                node_id = raw_input('# PgSQL node NodeID / FQDN [all]: ')
                dbname = raw_input('# DBname [all]: ')
                def_id = raw_input('# DefID []: ')

                while ack.lower() != 'yes' and ack.lower() != 'no':
                    ack = raw_input('# Are all values correct (yes/no): ')

                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------'
                print '[ABORTED] Command interrupted by the user.\n'
                return False

            if from_server_id == '':
                from_server_id = default_backup_server

            if to_server_id == '':
                to_server_id = default_backup_server

            if node_id.lower() in ['all','*','']:
                node_list = None
            else:
                node_list = node_id.strip().replace(' ','').split(',')

            if dbname.lower() in ['all','*','']:
                dbname_list = None
            else:
                dbname_list = dbname.strip().replace(' ','').split(',')

            if def_id.lower() in ['all','*','']:
                def_id_list = None
            else:
                def_id_list = def_id.strip().replace(' ','').split(',')

            if ack.lower() == 'yes':

                try:
                    self.db.move_backup_definition(from_server_id,to_server_id,node_list,dbname_list,def_id_list)

                    print '[DONE] Moving backup definitions from backup server [' + from_server_id + '] to backup server [' + to_server_id + ']\n'

                except Exception as e:
                    self.processing_error('[ERROR]: Could not move backup definitions from backup server [' + from_server_id + '] to backup server [' + to_server_id + ']\n')

            elif ack.lower() == 'no':

                print '[ABORTED] Command interrupted by the user.\n'


        #
        # Command with parameters
        #

        elif len(arg_list) == 5:

            from_server_id = arg_list[0]
            to_server_id = arg_list[1]
            node_id = arg_list[2]
            dbname = arg_list[3]
            def_id = arg_list[4]

            if from_server_id == '':
                from_server_id = default_backup_server

            if to_server_id == '':
                to_server_id = default_backup_server

            if node_id.lower() in ['all','*','']:
                node_list = None
            else:
                node_list = node_id.strip().replace(' ','').split(',')

            if dbname.lower() in ['all','*','']:
                dbname_list = None
            else:
                dbname_list = dbname.strip().replace(' ','').split(',')

            if def_id.lower() in ['all','*','']:
                def_id_list = None
            else:
                def_id_list = def_id.strip().replace(' ','').split(',')

            try:
                self.db.move_backup_definition(from_server_id,to_server_id,node_list,dbname_list,def_id_list)

                print '[DONE] Moving backup definitions from backup server [' + from_server_id + '] to backup server [' + to_server_id + ']\n'

            except Exception as e:
                self.processing_error('[ERROR]: Could not move backup definitions from backup server [' + from_server_id + '] to backup server [' + to_server_id + ']\n')

        else:
            self.processing_error('\n[ERROR] - Wrong number of parameters used.\n          Type help or ? to list commands\n')

        print


    # ############################################
    # Method do_clear
    # ############################################

    def do_clear(self,args):
        '''
        DESCRIPTION:
        Clears the screen and shows the welcome banner.

        COMMAND:
        clear

        '''

        os.system('clear')
        print self.intro


    # ############################################
    # Method default
    # ############################################

    def default(self,line):
        self.processing_error('\n[ERROR] - Unknown command: [' + line + '].\n          Type help or \? to list commands\n')
        print


    # ############################################
    # Method emptyline
    # ############################################

    def emptyline(self):
        pass


    # ############################################
    # Method precmd
    # ############################################

    def precmd(self, line_in):

        if line_in.strip() != '':
            split_line = line_in.strip().split()

            if split_line[0] not in ['EOF','shell','SHELL','\!']:
                line_out = line_in.strip().lower()
            else:
                line_out = line_in.strip()

            if split_line[0] == '\h':
                line_out = line_out.replace('\h','help')
            elif split_line[0] == '\?':
                line_out = line_out.replace('\?','help')
            elif split_line[0] == '\!':
                line_out = line_out.replace('\!','shell')
            elif line_out == '\s':
                line_out = 'show_history'
            elif line_out == '\q':
                line_out = 'quit'

            self._hist += [ line_out ]

        else:
            line_out = ''

        return cmd.Cmd.precmd(self, line_out)


    # ############################################
    # Method do_shell
    # ############################################

    def do_shell(self, line):
        '''
        DESCRIPTION:
        This command runs a command in the operative system

        COMMAND:
        shell [command]

        [command]:
        ----------
        Any command that can be run in the operative system.

        '''

        try:
            proc = subprocess.Popen([line],stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=True)
            output, errors = proc.communicate()
            print output,errors
            print

        except Exception as e:
            self.processing_error('[ERROR]: Problems running [' + line + ']\n')
            print


    # ############################################
    # Method do_quit
    # ############################################

    def do_quit(self, args):
        '''
        DESCRIPTION:
        Quits/terminate the PgBackMan shell.

        COMMAND:
        quit

        '''

        print '\nDone, thank you for using PgBackMan'
        return True


    # ############################################
    # Method do_EOF
    # ############################################

    def do_EOF(self, line):
        '''
        DESCRIPTION:
        Quits/terminate the PgBackMan shell.

        COMMAND:
        EOF

        '''

        print
        print '\nDone, thank you for using PgBackMan'
        return True


    # ############################################
    # Method do_hist
    # ############################################

    def do_show_history(self, args):
        '''
        DESCRIPTION:
        This command shows the list of commands that have been entered
        during the PgBackMan shell session.

        COMMAND:
        show_history

        '''

        cnt = 0
        print

        for line in self._hist:
            print '[' + str(cnt) + ']: ' + line
            cnt = cnt +1

        print

    # ############################################
    # Method preloop
    # ############################################

    def preloop(self):
        '''
        Initialization before prompting user for commands.
        '''

        cmd.Cmd.preloop(self)   ## sets up command completion
        self._hist    = []      ## No history yet
        self._locals  = {}      ## Initialize execution namespace for user
        self._globals = {}


    # ############################################
    # Method help_shortcuts
    # ############################################

    def help_shortcuts(self):
        '''Help information about shortcuts in PgBackMan'''

        print '''
        Shortcuts in PgBackMan:

        \h [COMMAND] - Help on syntax of PgBackMan commands
        \? [COMMAND] - Help on syntax of PgBackMan commands

        \s - display history
        \q - quit PgBackMan shell

        \! [COMMAND] - Execute command in shell

        '''

    # ############################################
    # Method help_shortcuts
    # ############################################

    def help_support(self):
        '''Help information about PgBackMan support'''

        print '''
        The latest information and versions of PgBackMan can be obtained
        from: https://github.com/jvaskonen/pgbackman

        Mailing list
        ------------
        Questions or comments for the PgBackMan community can be sent
        to the mailing list by using the email address
        pgbackman@googlegroups.com.

        The archive can be found on the web for the mailing list on
        Google Groups:
        https://groups.google.com/forum/#!forum/pgbackman

        Bug reports / Feature request
        -----------------------------
        If you find a bug or have a feature request, file them on
        GitHub / pgbackman:
        https://github.com/jvaskonen/pgbackman/issues

        IRC channel
        -----------
        If the documentation is not enough and you need in-person
        help, you can try the #pgbackman channel on the Freenode IRC
        server (irc.freenode.net).

        '''


    # ############################################
    # Method handler
    # ############################################

    def signal_handler_sigint(self,signum, frame):
        cmd.Cmd.onecmd(self,'quit')
        sys.exit(0)


    # ############################################
    # Method
    # ############################################

    def generate_output(self,cur,colnames,left_columns,result_type):
        '''A function to print the output from show_* commands'''

        if self.output_format == 'table':

            x = PrettyTable(colnames)
            x.padding_width = 1

            for column in left_columns:
                x.align[column] = "l"

            for records in cur:
                columns = []

                for index in range(len(colnames)):
                    columns.append(records[index])

                x.add_row(columns)

            print x.get_string()
            print

        elif self.output_format == 'csv':

            print ','.join(colnames).lower().replace(' ','_').replace(',id.,',',backup_server_id,').replace(',id,',',pgsql_node_id,')


            for records in cur:
                columns = []

                for index in range(len(colnames)):
                    columns.append(str(records[index]))

                print ','.join(columns)

        elif self.output_format == 'json':

            output = dict()
            entries = []

            for records in cur:
                attributes = OrderedDict()

                for index in range(len(colnames)):

                    #
                    # id. and id attributtes do not say anything in a
                    # json output. Change these values so it is easier
                    # to understand the meaning of them.
                    #

                    if colnames[index].lower() == 'id.':
                        attr = 'backup_server_id'
                    elif colnames[index].lower() == 'id':
                        attr = 'pgsql_node_id'
                    else:
                        attr = colnames[index].lower().replace(' ','_')

                    attributes[attr]=str(records[index])

                entries.append(attributes)

            output = {result_type:entries}

            print json.dumps(output,sort_keys=False,indent=2)


    # ############################################
    # Method
    # ############################################

    def generate_unique_output(self,result,result_type):
        ''''''

        if self.output_format == 'table':

            x = PrettyTable([".",".."],header = False)
            x.align["."] = "r"
            x.align[".."] = "l"
            x.padding_width = 1

            for key,value in result.iteritems():
                columns = []

                columns.append((key + ':').replace('#:','').replace('#',''))
                columns.append(str(value))

                x.add_row(columns)

            print x.get_string()
            print

        elif self.output_format == 'csv':

            colnames = []
            values = []

            for key,value in result.iteritems():

                if key.find('#') == -1:
                    colnames.append(str(key.lower().replace(' ','_')))
                    values.append(str(value))

            print ','.join(colnames)
            print ','.join(values)

        elif self.output_format == 'json':

            output = dict()
            entries = []
            attributes = OrderedDict()

            for key,value in result.iteritems():

                if key.find('#') == -1:
                    attributes[key.lower().replace(' ','_')]=str(value)

            entries.append(attributes)
            output = {result_type:entries}

            print json.dumps(output,sort_keys=False,indent=2)


    # ############################################
    # Method check_minutes_interval()
    # ############################################

    def check_minutes_interval(self,interval):
        '''Check if this a valid minute interval, min-min'''

        if len(interval.split('-')) == 2:

            (a,b) = interval.split('-')

            if a.isdigit() and b.isdigit():
                min_from = int(a)
                min_to = int(b)

                if min_from <= min_to:
                    if min_from >= 0 and min_from <= 59:
                        if min_to >= 0 and min_to <= 59:
                            return True
                        else:
                            return False
                    else:
                        return False
                else:
                    return False
            else:
                return False
        else:
            return False


    # ############################################
    # Method check_hours_interval()
    # ############################################

    def check_hours_interval(self,interval):
        '''Check if this a valid hour interval, hour-hour'''

        if len(interval.split('-')) == 2:

            (a,b) = interval.split('-')

            if a.isdigit() and b.isdigit():
                hour_from = int(a)
                hour_to = int(b)

                if hour_from <= hour_to:
                    if hour_from >= 0 and hour_from <= 23:
                        if hour_to >= 0 and hour_to <= 23:
                            return True
                        else:
                            return False
                    else:
                        return False
                else:
                    return False
            else:
                return False
        else:
            return False


    # ############################################
    # Method self.processing_error
    # ############################################

    def processing_error(self,message):
        '''Process error messages'''

        print message

        if self.execution_modus == 'non-interactive':
            sys.exit(1)



    # ############################################
    # Method check_port
    # ############################################

    def check_port(self,digit):

        if digit.isdigit():
            return True
        else:
            print '[ERROR]: Port value should be an INTEGER\n'
            return False


    # ############################################
    # Method get_default_backup_server
    # ############################################

    def get_default_backup_server(self):
        '''
        Return the backup server defined in pgbackman.conf or the server
        running pgbackman
        '''

        try:

            if self.conf.backup_server != '':
                backup_server_fqdn = self.conf.backup_server
            else:
                backup_server_fqdn = socket.getfqdn()

            return backup_server_fqdn

        except Exception as e:
            return ''


    # ############################################
    # Method get_pgbackman_software_version_tag
    # ############################################

    def get_pgbackman_software_version_tag(self):
        '''Get pgbackman software version'''

        try:
            return pgbackman.version.__version__.split(':')[1]

        except Exception as e:
            raise e


    # ############################################
    # Method get_pgbackman_software_version_number
    # ############################################

    def get_pgbackman_software_version_number(self):
        '''Get pgbackman software version'''

        try:
            return pgbackman.version.__version__.split(':')[0]

        except Exception as e:
            raise e


    # ############################################
    # Method get_pgbackman_database_version
    # ############################################

    def get_pgbackman_database_version_info(self):
        '''Get pgbackman database version'''

        try:

            for version in self.db.get_pgbackman_database_version():
                return version

        except Exception as e:
            raise e

    # ############################################
    # Method get_backup_server_running_pgbackman()
    # ############################################

    def get_backup_server_running_pgbackman(self):

        #
        # Checking if this backup server is registered in pgbackman
        #

        if self.conf.backup_server != '':
            backup_server_fqdn = self.conf.backup_server
        else:
            backup_server_fqdn = socket.getfqdn()

        try:
            self.backup_server_id = self.db.get_backup_server_id(backup_server_fqdn)
            self.logs.logger.info('Backup server: %s is registered in pgbackman',backup_server_fqdn)

        except psycopg2.Error as e:
            self.logs.logger.critical('Cannot find backup server %s in pgbackman. Stopping the upgrade of pgbackman.',backup_server_fqdn)
            sys.exit(1)


    # ##################################################
    # Function process_pending_backup_catalog_log_file()
    # ##################################################

    def process_pending_backup_catalog_log_file_from_1_0_0(self,db,backup_server_id):
        '''Process all pending backup catalog log files in the server '''

        role_list = []

        self.logs.logger.info('Processing pending backup catalog log files from version 1.0.0 before upgrading to a new version')

        try:
            db.pg_connect()

            root_backup_partition = db.get_backup_server_config_value(backup_server_id,'root_backup_partition')
            pending_catalog = root_backup_partition + '/pending_updates'

            for pending_log_file in os.listdir(pending_catalog):
                if pending_log_file.find('backup_jobs_pending_log_updates_nodeid') != -1:
                    with open(pending_catalog + '/' + pending_log_file,'r') as pending_file:
                        for line in pending_file:
                            parameters = line.split('::')

                            if len(parameters) == 24:

                                #
                                # Fix when def_id and snapshot_id are like ''. This is not a valid
                                # integer value
                                #

                                def_id = parameters[0]
                                snapshot_id = parameters[21]

                                if def_id == '':
                                    def_id = None
                                elif snapshot_id == '':
                                    snapshot_id = None

                                # Generate role list

                                role_list = parameters[22].split(' ')

                                #
                                # Updating the database with the information in the pending file
                                #

                                db.register_backup_catalog_1_0_0(def_id,
                                                           parameters[1],
                                                           parameters[2],
                                                           parameters[3],
                                                           parameters[4],
                                                           parameters[5],
                                                           parameters[6],
                                                           parameters[7],
                                                           parameters[8],
                                                           parameters[9],
                                                           parameters[10],
                                                           parameters[11],
                                                           parameters[12],
                                                           parameters[13],
                                                           parameters[14],
                                                           parameters[15],
                                                           parameters[16],
                                                           parameters[17],
                                                           parameters[18],
                                                           parameters[19],
                                                           parameters[20],
                                                           snapshot_id,
                                                           role_list,
                                                           parameters[23].replace('\n',''))

                                self.logs.logger.info('Backup job catalog for DefID: %s or snapshotID: %s in pending file %s updated in the database',def_id,snapshot_id,pending_log_file)

                                #
                                # Deleting the pending file if we can update the database with
                                # the information in the file
                                #

                                print '[OK] File: ' + pending_catalog + '/' + pending_log_file + ' processed.'

                                os.unlink(pending_catalog + '/' + pending_log_file)
                                self.logs.logger.info('Pending backup file: %s deleted before upgrading to a new version',pending_log_file)

                            else:
                                self.logs.logger.error('Wrong format in pending backup file: %s',pending_log_file)

        except psycopg2.OperationalError as e:
            raise e
        except Exception as e:
            self.logs.logger.error('Problems processing pending backup files - %s',e)


    # ############################################
    # Method check_pgbackman_database_version
    # ############################################

    def check_pgbackman_database_version(self):
        '''Check pgbackman database version'''

        ack_input = ''

        try:
            software_version_tag = 'v_'+ self.software_version_tag.replace('.','_')
            software_version_number = int(self.software_version_number)
            database_version_tag = self.get_pgbackman_database_version_info()[2]
            database_version_number = int(self.get_pgbackman_database_version_info()[1])

        except Exception as e:
            print '''
ERROR: Problems getting the pgbackman database version used by this PgBackMan installation.
The execution is aborted to avoid problems in case there is a mismatch between the version
of the software and the version of the database.

''',e,'\n'

            sys.exit(1)

        if software_version_number > database_version_number:

            print '#################'
            print 'A T T E N T I O N'
            print '#################'
            print

            print 'The PgBackMan software version [' + str(software_version_number) + ':' + software_version_tag + '] is different from'
            print 'the PgBackMan database version [' + str(database_version_number) + ':' + database_version_tag + '].'
            print

            self.logs.logger.error('PgBackMan software version %s is different from PgBackMan database version %s',
                                   str(software_version_number) + ':' + software_version_tag,
                                   str(database_version_number) + ':' + database_version_tag)

            try:
                while ack_input.lower() != 'yes' and ack_input.lower() != 'no':
                    ack_input = raw_input('# Do you want to upgrade the PgBackMan database to version: [' + str(software_version_number) + ':' + software_version_tag + '] (yes/no): ')

            except Exception as e:
                sys.exit(1)

            if ack_input.lower() == 'yes':

                self.get_backup_server_running_pgbackman()

                root_backup_partition = self.db.get_backup_server_config_value(self.backup_server_id,'root_backup_partition')
                pending_catalog = root_backup_partition + '/pending_updates'

                print
                print '###################################################################'
                print 'Processing old pending files under ' + pending_catalog
                print '###################################################################'
                print

                self.process_pending_backup_catalog_log_file_from_1_0_0(self.db,self.backup_server_id)
                self.update_pgbackman_database_version()

            elif ack_input.lower() == 'no':
                print
                print '[EXITING]: PgBackMan can not run with different PgBackMan software'
                print '           and PgBackMan database versions.'
                print

                self.logs.logger.info('Database upgrade not confirmed by the user. Exiting!')

                sys.exit(1)

        elif software_version_number < database_version_number:

            print '#################'
            print 'A T T E N T I O N'
            print '#################'
            print

            print 'The PgBackMan software version [' + str(software_version_number) + ':' + software_version_tag + '] is different from '
            print 'the PgBackMan database version [' + str(database_version_number) + ':' + database_version_tag + '].'

            self.logs.logger.error('PgBackMan software version %s is different from PgBackMan database version %s',
                                   str(software_version_number) + ':' + software_version_tag,
                                   str(database_version_number) + ':' + database_version_tag)

            self.logs.logger.info('Upgrade PgBackMan software to version %s. Exiting!',database_version_tag )

            print
            print '[EXITING]: PgBackMan can not run with different PgBackMan software'
            print '           and PgBackMan database versions.'
            print '           Upgrade the PgBackMan software to version [' + str(database_version_number) + ':' + database_version_tag + '].'
            print

            sys.exit(1)


    # ############################################
    # Method update_database_version
    # ############################################

    def update_pgbackman_database_version(self):
        '''Update pgbackman database version'''

        try:

            software_version_tag = 'v_'+ self.software_version_tag.replace('.','_')
            software_version_number = int(self.software_version_number)
            database_version_number = int(self.get_pgbackman_database_version_info()[1])

        except Exception as e:
            print '''
ERROR: Problems getting the pgbackman database version used by this PgBackMan installation.
The execution is aborted to avoid problems in case there is a mismatch between the version
of the software and the version of the database.

''',e,'\n'
            sys.exit(1)

        check_file_errors = 0

        self.logs.logger.info('Upgrading the PgBackMan database')

        print
        print '############################'
        print 'Upgrading PgBackMan database'
        print '############################'
        print

        for n in range(database_version_number+1,software_version_number+1):

            file = self.conf.database_source_dir + '/pgbackman_' + str(n) + '.sql'

            if os.path.exists(file):
                print '[OK]: File: ' + file + ' exists.'
                self.logs.logger.info('File: %s exists',file)

            else:
                print '[ERROR]: File: ' + file + ' does not exist.'
                self.logs.logger.error('File: %s does not exist',file)

                check_file_errors = check_file_errors + 1

        if check_file_errors > 0:
            print
            print '[ABORTING]: Some database source files needed to upgrade do not exist.'
            print

            self.logs.logger.error('Aborting the PgBackMan database upgrade. Exiting!')
            sys.exit(1)

        elif check_file_errors == 0:

            print

            for n in range(database_version_number+1,software_version_number+1):

                file = self.conf.database_source_dir + '/pgbackman_' + str(n) + '.sql'

                try:
                    self.db.run_sql_file(file)

                    print '[OK]: File ' + file + ' installed.'
                    self.logs.logger.info('File: %s installed',file)

                except Exception as e:
                    print '[ERROR]: Problems upgrading to: ' + file
                    print 'Exception: ' + str(e)
                    print

                    self.logs.logger.error('Problems upgrading to: %s - %s',file,e)
                    self.logs.logger.error('Aborting the PgBackMan database upgrade. Exiting!')
                    sys.exit(1)

            self.logs.logger.info('PgBackMan upgraded to version %s',str(software_version_number) + ':' + software_version_tag)

if __name__ == '__main__':

    signal.signal(signal.SIGINT, PgbackmanCli().signal_handler_sigint)
    signal.signal(signal.SIGTERM, PgbackmanCli().signal_handler_sigint)
    PgbackmanCli().cmdloop()
