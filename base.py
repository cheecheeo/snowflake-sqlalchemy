#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012-2016 Snowflake Computing Inc. All right reserved.
#

import re
from sqlalchemy import exc as sa_exc
from sqlalchemy import util as sa_util
from sqlalchemy.engine import default, reflection
from sqlalchemy.sql import compiler
from sqlalchemy.sql import expression
from sqlalchemy.sql.elements import quoted_name
from sqlalchemy.types import (CHAR, CLOB, DATE, DATETIME, INTEGER,
                              SMALLINT, BIGINT, DECIMAL, TIME, TIMESTAMP,
                              VARCHAR, BINARY, BOOLEAN,
                              FLOAT, REAL)
from ..connector import errors as sf_errors
from ..connector.constants import UTF8

RESERVED_WORDS = frozenset([
    "ALL",  # ANSI Reserved words
    "ALTER",
    "AND",
    "ANY",
    "AS",
    "BETWEEN",
    "BY",
    "CHECK",
    "COLUMN",
    "CONNECT",
    "CREATE",
    "CURRENT",
    "DELETE",
    "DISTINCT",
    "DROP",
    "ELSE",
    "EXISTS",
    "FOR",
    "FROM",
    "GRANT",
    "GROUP",
    "HAVING",
    "IN",
    "INSERT",
    "INTERSECT",
    "INTO",
    "IS",
    "LIKE",
    "NOT",
    "NULL",
    "OF",
    "ON",
    "OR",
    "ORDER",
    "REVOKE",
    "ROW",
    "ROWS",
    "SELECT",
    "SET",
    "START",
    "TABLE",
    "THEN",
    "TO",
    "TRIGGER",
    "UNION",
    "UNIQUE",
    "UPDATE",
    "VALUES",
    "WHENEVER",
    "WHERE",
    "WITH",
    "REGEXP", "RLIKE", "SOME",  # Snowflake Reserved words
    "MINUS", "INCREMENT",  # Oracle reserved words
])

colspecs = {
}

ischema_names = {
    'BIGINT': BIGINT,
    'BINARY': BINARY,
    # 'BIT': BIT,
    'BOOLEAN': BOOLEAN,
    'CHAR': CHAR,
    'CHARACTER': CHAR,
    'DATE': DATE,
    'DATETIME': DATETIME,
    'DEC': DECIMAL,
    'DECIMAL': DECIMAL,
    'DOUBLE': FLOAT,
    'FIXED': DECIMAL,
    'FLOAT': FLOAT,
    'INT': INTEGER,
    'INTEGER': INTEGER,
    'NUMBER': DECIMAL,
    # 'OBJECT': ?
    'REAL': REAL,
    'BYTEINT': SMALLINT,
    'SMALLINT': SMALLINT,
    'STRING': VARCHAR,
    'TEXT': VARCHAR,
    'TIME': TIME,
    'TIMESTAMP': TIMESTAMP,
    'TIMESTAMP_LTZ': TIMESTAMP,
    'TIMESTAMP_TZ': TIMESTAMP,
    'TIMESTAMP_NTZ': TIMESTAMP,
    'TINYINT': SMALLINT,
    'VARBINARY': BINARY,
    'VARCHAR': VARCHAR,
    'VARIANT': CLOB,
    'OBJECT': INTEGER,
    #    'ARRAY': CLOB,
}

# Snowflake DML:
# - UPDATE
# - INSERT
# - DELETE
# - MERGE
AUTOCOMMIT_REGEXP = re.compile(
    r'\s*(?:UPDATE|INSERT|DELETE|MERGE)',
    re.I | re.UNICODE)


class SnowflakeIdentifierPreparer(compiler.IdentifierPreparer):
    reserved_words = set([x.lower() for x in RESERVED_WORDS])

    def __init__(self, dialect, **kw):
        quote = '"'

        super(SnowflakeIdentifierPreparer, self).__init__(
            dialect,
            initial_quote=quote,
            escape_quote=quote)

    def _quote_free_identifiers(self, *ids):
        """
        Unilaterally identifier-quote any number of strings.
        """
        return tuple([self.quote(i) for i in ids if i is not None])


class SnowflakeCompiler(compiler.SQLCompiler):
    def visit_sequence(self, sequence):
        return (self.dialect.identifier_preparer.format_sequence(sequence) +
                ".nextval")


class SnowflakeExecutionContext(default.DefaultExecutionContext):
    def fire_sequence(self, seq, type_):
        return self._execute_scalar(
            "SELECT " +
            self.dialect.identifier_preparer.format_sequence(seq) +
            ".nextval", type_)

    def should_autocommit_text(self, statement):
        return AUTOCOMMIT_REGEXP.match(statement)

    @sa_util.memoized_property
    def should_autocommit(self):
        autocommit = self.execution_options.get('autocommit',
                                                not self.compiled and
                                                self.statement and
                                                expression.PARSE_AUTOCOMMIT
                                                or False)

        if autocommit is expression.PARSE_AUTOCOMMIT:
            return self.should_autocommit_text(self.unicode_statement)
        else:
            return autocommit and not self.isddl


class SnowflakeDDLCompiler(compiler.DDLCompiler):
    def get_column_specification(self, column, **kwargs):
        """
        Gets Column specifications
        """
        colspec = [
            self.preparer.format_column(column),
            self.dialect.type_compiler.process(
                column.type, type_expression=column)
        ]

        if not column.nullable:
            colspec.append('NOT NULL')

        default = self.get_column_default_string(column)
        if default is not None:
            colspec.append('DEFAULT ' + default)

        # TODO: This makes the first INTEGER column AUTOINCREMENT.
        # But the column is not really considered so unless
        # postfetch_lastrowid is enabled. But it is very unlikely to happen...
        if column.table is not None \
                and column is column.table._autoincrement_column and \
                        column.server_default is None:
            colspec.append('AUTOINCREMENT')

        return ' '.join(colspec)


class SnowflakeDialect(default.DefaultDialect):
    name = 'snowflake'
    max_identifier_length = 65535

    encoding = UTF8
    default_paramstyle = 'pyformat'
    colspecs = colspecs
    ischema_names = ischema_names

    # all str types must be converted in Unicode
    convert_unicode = True

    # Indicate whether the DB-API can receive SQL statements as Python
    #  unicode strings
    supports_unicode_statements = True
    supports_unicode_binds = True
    returns_unicode_strings = True
    description_encoding = None

    # No lastrowid support. See SNOW-11155
    postfetch_lastrowid = False

    # Indicate whether the dialect properly implements rowcount for
    #  ``UPDATE`` and ``DELETE`` statements.
    supports_sane_rowcount = True

    # Indicate whether the dialect properly implements rowcount for
    # ``UPDATE`` and ``DELETE`` statements when executed via
    # executemany.
    supports_sane_multi_rowcount = True

    # NUMERIC type returns decimal.Decimal
    supports_native_decimal = True

    # The dialect supports a native boolean construct.
    # This will prevent types.Boolean from generating a CHECK
    # constraint when that type is used.
    supports_native_boolean = True

    # The dialect supports ``ALTER TABLE``.
    supports_alter = True

    # The dialect supports CREATE SEQUENCE or similar.
    supports_sequences = True

    # The dialect supports a native ENUM construct.
    supports_native_enum = False

    preparer = SnowflakeIdentifierPreparer
    ddl_compiler = SnowflakeDDLCompiler
    statement_compiler = SnowflakeCompiler
    execution_ctx_cls = SnowflakeExecutionContext

    # indicates symbol names are
    # UPPERCASEd if they are case insensitive
    # within the database.
    # if this is True, the methods normalize_name()
    # and denormalize_name() must be provided.
    requires_name_normalize = True

    @classmethod
    def dbapi(cls):
        from snowflake import connector
        return connector

    def create_connect_args(self, url):
        opts = url.translate_connect_args(username='user')
        if 'database' in opts:
            name_spaces = opts['database'].split('/')
            if len(name_spaces) == 1:
                pass
            elif len(name_spaces) == 2:
                opts['database'] = name_spaces[0]
                opts['schema'] = name_spaces[1]
            else:
                raise sa_exc.ArgumentError(
                    "Invalid name space is specified: {0}".format(
                        opts['database']
                    ))
        if '.' not in opts['host']:
            opts['account'] = opts['host']
            opts['host'] = opts['host'] + '.snowflakecomputing.com'
            opts['port'] = '443'
        opts['autocommit'] = False  # autocommit is disabled by default
        opts.update(url.query)
        return ([], opts)

    def has_table(self, connection, table_name, schema=None):
        """
        Checks if the table exists
        """
        return self._has_object(connection, 'TABLE', table_name, schema)

    def has_sequence(self, connection, sequence_name, schema=None):
        """
        Checks if the sequence exists
        """
        return self._has_object(connection, 'SEQUENCE', sequence_name, schema)

    def _has_object(self, connection, object_type, object_name, schema=None):

        full_name = self._denormalize_quote_join(schema, object_name)

        try:
            results = connection.execute("DESC {0} {1}".format(
                object_type, full_name))
            row = results.fetchone()
            have = row is not None
            return have
        except sa_exc.DBAPIError as e:
            if e.orig.__class__ == sf_errors.ProgrammingError:
                return False
            raise

    def normalize_name(self, name):
        if name is None:
            return None
        if name.upper() == name and not \
                self.identifier_preparer._requires_quotes(name.lower()):
            return name.lower()
        elif name.lower() == name:
            return quoted_name(name, quote=True)
        else:
            return name

    def denormalize_name(self, name):
        if name is None:
            return None
        elif name.lower() == name and not \
                self.identifier_preparer._requires_quotes(name.lower()):
            name = name.upper()
        return name

    def _denormalize_quote_join(self, *idents):
        return '.'.join(
            self.identifier_preparer._quote_free_identifiers(*idents))

    @staticmethod
    def _map_name_to_idx(result):
        name_to_idx = {}
        for idx, col in enumerate(result.cursor.description):
            name_to_idx[col[0]] = idx
        return name_to_idx

    @reflection.cache
    def get_indexes(self, connection, table_name, schema=None, **kw):
        """
        Gets all indexes
        """
        # no index is supported by Snowflake
        return []

    @reflection.cache
    def get_primary_keys(self, connection, table_name, schema=None, **kw):
        schema = schema or self.default_schema_name
        if not schema:
            row = connection.execute("SELECT CURRENT_SCHEMA()").fetchone()
            schema = self.normalize_name(row[0])
        full_table_name = self._denormalize_quote_join(schema, table_name)

        result = connection.execute(
            "DESCRIBE TABLE {0}".format(full_table_name))
        n2i = self.__class__._map_name_to_idx(result)

        primary_key_info = {
            'constrained_columns': [],
            'name': None  # optional
        }
        for row in result:
            column_name = row[n2i['name']]
            is_primary_key = row[n2i['primary key']] == 'Y'
            if is_primary_key:
                primary_key_info['constrained_columns'].append(
                    self.normalize_name(column_name))

        return primary_key_info

    @reflection.cache
    def get_foreign_keys(self, connection, table_name, schema=None, **kw):
        """
        Gets all foreign keys
        """
        schema = schema or self.default_schema_name
        row = connection.execute("SELECT CURRENT_DATABASE(), "
                                 "CURRENT_SCHEMA()").fetchone()

        full_schema_name = self._denormalize_quote_join(
            row[0], schema if schema else row[1])

        result = connection.execute(
            "SHOW IMPORTED KEYS IN SCHEMA {0}".format(full_schema_name)
        )
        n2i = self.__class__._map_name_to_idx(result)

        foreign_key_map = {}
        for row in result:
            name = row[n2i['fk_name']]
            constrained_table = self.normalize_name(row[n2i['fk_table_name']])
            if constrained_table == table_name:
                constrained_column = self.normalize_name(
                    row[n2i['fk_column_name']])
                referred_schema = self.normalize_name(
                    row[n2i['pk_schema_name']])
                referred_table = self.normalize_name(row[n2i['pk_table_name']])
                referred_column = self.normalize_name(
                    row[n2i['pk_column_name']])

                if not name in foreign_key_map:
                    foreign_key_map[name] = {
                        'constrained_columns': [constrained_column],
                        'referred_schema': referred_schema,
                        'referred_table': referred_table,
                        'referred_columns': [referred_column],
                    }
                else:
                    foreign_key_map[name]['constrained_columns'].append(
                        constrained_column)
                    foreign_key_map[name]['referred_columns'].append(
                        referred_column)
        ret = []
        for name in foreign_key_map:
            foreign_key = {
                'name': name,
            }
            foreign_key.update(foreign_key_map[name])
            ret.append(foreign_key)
        return ret

    @reflection.cache
    def get_columns(self, connection, table_name, schema=None, **kw):
        """
        Gets all column info given the table info
        """
        schema = schema or self.default_schema_name
        if not schema:
            row = connection.execute("SELECT CURRENT_SCHEMA()").fetchone()
            schema = self.normalize_name(row[0])

        full_table_name = self._denormalize_quote_join(schema, table_name)

        result = connection.execute(
            'DESCRIBE TABLE {0}'.format(full_table_name))
        n2i = self.__class__._map_name_to_idx(result)

        column_map = {}
        for row in result:
            column_name = row[n2i['name']]
            is_primary_key = row[n2i['primary key']] == 'Y'
            column_map[column_name] = is_primary_key

        columns = []
        result = connection.execute(
            """
SELECT ic.column_name,
       ic.data_type,
       ic.character_maximum_length,
       ic.numeric_precision,
       ic.numeric_scale,
       ic.is_nullable,
       ic.column_default,
       ic.is_identity
  FROM information_schema.columns ic
 WHERE ic.table_schema=%(table_schema)s
   AND ic.table_name=%(table_name)s
 ORDER BY ic.ordinal_position
            """,
            table_schema=self.denormalize_name(schema),
            table_name=self.denormalize_name(
                table_name))
        for (colname, coltype, character_maximum_length, numeric_precision,
             numeric_scale, is_nullable, column_default, is_identity) in result:
            cdict = {
                'name': self.normalize_name(colname),
                'type': self.ischema_names.get(coltype),
                'nullable': is_nullable == 'YES',
                'default': column_default,
                'autoincrement': is_identity == 'YES',
                'primary_key': column_map[colname],
            }

            columns.append(cdict)
        return columns

    @reflection.cache
    def get_table_names(self, connection, schema=None, **kw):
        """
        Gets all table names.
        """
        schema = schema or self.default_schema_name
        if schema:
            cursor = connection.execute(
                "SHOW TABLES IN {0}".format(
                    self._denormalize_quote_join(schema)))
        else:
            cursor = connection.execute("SHOW TABLES")

        return [self.normalize_name(row[1]) for row in cursor]

    @reflection.cache
    def get_view_names(self, connection, schema=None, **kw):
        """
        Gets all view names
        """
        schema = schema or self.default_schema_name
        if schema:
            cursor = connection.execute(
                "SHOW VIEWS IN {0}".format(
                    self._denormalize_quote_join((schema))))
        else:
            cursor = connection.execute("SHOW VIEWS")

        return [self.normalize_name(row[1]) for row in cursor]

    @reflection.cache
    def get_view_definition(self, connection, view_name, schema=None, **kw):
        """
        Gets the view definition
        """
        schema = schema or self.default_schema_name
        if schema:
            cursor = connection.execute("SHOW VIEWS LIKE '{0}' IN {1}".format(
                self._denormalize_quote_join(view_name),
                self._denormalize_quote_join(schema)))
        else:
            cursor = connection.execute(
                "SHOW VIEWS LIKE '{0}'".format(
                    self._denormalize_quote_join(view_name)))

        n2i = self.__class__._map_name_to_idx(cursor)
        try:
            ret = cursor.fetchone()
            if ret:
                return ret[n2i['text']]
        except:
            pass
        return None

    def get_temp_table_names(self, connection, schema=None, **kw):
        schema = schema or self.default_schema_name
        if schema:
            cursor = connection.execute("SHOW TABLES IN {0}".format(
                self._denormalize_quote_join(schema)))
        else:
            cursor = connection.execute("SHOW TABLES")

        ret = []
        n2i = self.__class__._map_name_to_idx(cursor)
        for row in cursor:
            if row[n2i['kind']] == 'TEMPORARY':
                ret.append(self.normalize_name(row[n2i['name']]))

        return ret


dialect = SnowflakeDialect
