import os
from pathlib import Path


import pytest
from IPython.core.error import UsageError

from sql.parse import (
    connection_str_from_dsn_section,
    parse,
    without_sql_comment,
    split_args_and_sql,
    magic_args,
    escape_string_literals_with_colon_prefix,
    escape_string_slicing_notation,
    find_named_parameters,
    _connection_string,
    ConnectionsFile,
)


default_connect_args = {"options": "-csearch_path=test"}

PATH_TO_DSN_FILE = "src/tests/test_dsn_config.ini"


class DummyConfig:
    dsn_filename = Path("src/tests/test_dsn_config.ini")


def test_parse_no_sql():
    assert parse("will:longliveliz@localhost/shakes", PATH_TO_DSN_FILE) == {
        "connection": "will:longliveliz@localhost/shakes",
        "sql": "",
        "result_var": None,
        "return_result_var": False,
    }


def test_parse_with_sql():
    assert parse(
        "postgresql://will:longliveliz@localhost/shakes SELECT * FROM work",
        PATH_TO_DSN_FILE,
    ) == {
        "connection": "postgresql://will:longliveliz@localhost/shakes",
        "sql": "SELECT * FROM work",
        "result_var": None,
        "return_result_var": False,
    }


def test_parse_sql_only():
    assert parse("SELECT * FROM work", PATH_TO_DSN_FILE) == {
        "connection": "",
        "sql": "SELECT * FROM work",
        "result_var": None,
        "return_result_var": False,
    }


def test_parse_postgresql_socket_connection():
    assert parse("postgresql:///shakes SELECT * FROM work", PATH_TO_DSN_FILE) == {
        "connection": "postgresql:///shakes",
        "sql": "SELECT * FROM work",
        "result_var": None,
        "return_result_var": False,
    }


def test_expand_environment_variables_in_connection():
    os.environ["DATABASE_URL"] = "postgresql:///shakes"
    assert parse("$DATABASE_URL SELECT * FROM work", PATH_TO_DSN_FILE) == {
        "connection": "postgresql:///shakes",
        "sql": "SELECT * FROM work",
        "result_var": None,
        "return_result_var": False,
    }


def test_parse_shovel_operator():
    assert parse("dest << SELECT * FROM work", PATH_TO_DSN_FILE) == {
        "connection": "",
        "sql": "SELECT * FROM work",
        "result_var": "dest",
        "return_result_var": False,
    }


@pytest.mark.parametrize(
    "input_string",
    [
        "dest= << SELECT * FROM work",
        "dest = << SELECT * FROM work",
        "dest =<< SELECT * FROM work",
        "dest =        << SELECT * FROM work",
        "dest      =<< SELECT * FROM work",
        "dest =          << SELECT * FROM work",
        "dest=<< SELECT * FROM work",
        "dest=<<SELECT * FROM work",
        "dest    =<<SELECT * FROM work",
        "dest    =<<    SELECT * FROM work",
        "dest=   <<    SELECT * FROM work",
    ],
)
def test_parse_return_shovel_operator_with_equal(input_string, ip):
    result_var = {
        "connection": "",
        "sql": "SELECT * FROM work",
        "result_var": "dest",
        "return_result_var": True,
    }
    assert parse(input_string, PATH_TO_DSN_FILE) == result_var


@pytest.mark.parametrize(
    "input_string",
    [
        "dest<< SELECT * FROM work",
        "dest<<SELECT * FROM work",
        "dest    <<SELECT * FROM work",
        "dest    <<    SELECT * FROM work",
        "dest <<SELECT * FROM work",
        "dest << SELECT * FROM work",
    ],
)
def test_parse_return_shovel_operator_without_equal(input_string, ip):
    result_var = {
        "connection": "",
        "sql": "SELECT * FROM work",
        "result_var": "dest",
        "return_result_var": False,
    }
    assert parse(input_string, PATH_TO_DSN_FILE) == result_var


def test_parse_connect_plus_shovel():
    assert parse("sqlite:// dest << SELECT * FROM work", PATH_TO_DSN_FILE) == {
        "connection": "sqlite://",
        "sql": "SELECT * FROM work",
        "result_var": "dest",
        "return_result_var": False,
    }


def test_parse_early_newlines():
    assert parse("--comment\nSELECT *\n--comment\nFROM work", PATH_TO_DSN_FILE) == {
        "connection": "",
        "sql": "--comment\nSELECT *\n--comment\nFROM work",
        "result_var": None,
        "return_result_var": False,
    }


def test_parse_connect_shovel_over_newlines():
    assert parse("\nsqlite://\ndest\n<<\nSELECT *\nFROM work", PATH_TO_DSN_FILE) == {
        "connection": "sqlite://",
        "sql": "\nSELECT *\nFROM work",
        "result_var": "dest",
        "return_result_var": False,
    }


@pytest.mark.parametrize(
    "section, expected",
    [
        (
            "DB_CONFIG_1",
            "postgres://goesto11:seentheelephant@my.remote.host:5432/pgmain",
        ),
        (
            "DB_CONFIG_2",
            "mysql://thefin:fishputsfishonthetable@127.0.0.1/dolfin",
        ),
    ],
)
def test_connection_from_dsn_section(section, expected):
    result = connection_str_from_dsn_section(section=section, config=DummyConfig)
    assert result == expected


@pytest.mark.parametrize(
    "input_, expected",
    [
        ("", ""),
        (
            "drivername://user:pass@host:port/db",
            "drivername://user:pass@host:port/db",
        ),
        ("drivername://", "drivername://"),
        (
            "[DB_CONFIG_1]",
            "postgres://goesto11:seentheelephant@my.remote.host:5432/pgmain",
        ),
        ("DB_CONFIG_1", ""),
        ("not-a-url", ""),
    ],
    ids=[
        "empty",
        "full",
        "drivername",
        "section",
        "not-a-section",
        "not-a-url",
    ],
)
def test_connection_string(input_, expected):
    assert _connection_string(input_, "src/tests/test_dsn_config.ini") == expected


class Bunch:
    def __init__(self, **kwds):
        self.__dict__.update(kwds)


class ParserStub:
    opstrs = [
        [],
        ["-l", "--connections"],
        ["-x", "--close"],
        ["-c", "--creator"],
        ["-s", "--section"],
        ["-p", "--persist"],
        ["--append"],
        ["-a", "--connection_arguments"],
        ["-f", "--file"],
    ]
    _actions = [Bunch(option_strings=o) for o in opstrs]


parser_stub = ParserStub()


def test_without_sql_comment_plain():
    line = "SELECT * FROM author"
    assert without_sql_comment(parser=parser_stub, line=line) == line


def test_without_sql_comment_with_arg():
    line = "--file moo.txt --persist SELECT * FROM author"
    assert without_sql_comment(parser=parser_stub, line=line) == line


def test_without_sql_comment_with_comment():
    line = "SELECT * FROM author -- uff da"
    expected = "SELECT * FROM author"
    assert without_sql_comment(parser=parser_stub, line=line) == expected


def test_without_sql_comment_with_arg_and_comment():
    line = "--file moo.txt --persist SELECT * FROM author -- uff da"
    expected = "--file moo.txt --persist SELECT * FROM author"
    assert without_sql_comment(parser=parser_stub, line=line) == expected


def test_without_sql_comment_unspaced_comment():
    line = "SELECT * FROM author --uff da"
    expected = "SELECT * FROM author"
    assert without_sql_comment(parser=parser_stub, line=line) == expected


def test_without_sql_comment_dashes_in_string():
    line = "SELECT '--very --confusing' FROM author -- uff da"
    expected = "SELECT '--very --confusing' FROM author"
    assert without_sql_comment(parser=parser_stub, line=line) == expected


def test_without_sql_comment_with_arg_and_leading_comment():
    line = "--file moo.txt --persist --comment, not arg"
    expected = "--file moo.txt --persist"
    assert without_sql_comment(parser=parser_stub, line=line) == expected


def test_without_sql_persist():
    line = "--persist my_table --uff da"
    expected = "--persist my_table"
    assert without_sql_comment(parser=parser_stub, line=line) == expected


def complete_with_defaults(mapping):
    defaults = {
        "alias": None,
        "line": ["some-argument"],
        "connections": False,
        "close": None,
        "creator": None,
        "section": None,
        "persist": False,
        "persist_replace": False,
        "no_index": False,
        "append": False,
        "connection_arguments": None,
        "file": None,
        "interact": None,
        "save": None,
        "with_": None,
        "no_execute": False,
    }

    return {**defaults, **mapping}


@pytest.mark.parametrize(
    "line, cmd_from, expected_error_message",
    [
        (
            "duckdb:// --alias test1 --alias test2",
            "sql",
            (
                "Duplicate arguments in %sql. "
                "Please use only one of each of the following: --alias"
            ),
        ),
        (
            """histogram --table penguins.csv --column bill_length_mm
--column body_mass_g""",
            "sqlplot",
            (
                "Duplicate arguments in %sqlplot. "
                "Please use only one of each of the following: --column"
            ),
        ),
        (
            """bar --table penguins.csv --column bill_length_mm
--show-numbers --show-numbers""",
            "sqlplot",
            (
                "Duplicate arguments in %sqlplot. "
                "Please use only one of each of the following: --show-numbers"
            ),
        ),
    ],
)
def test_magic_args_raises_usageerror(
    load_penguin, ip, line, cmd_from, expected_error_message
):
    ALLOWED_DUPLICATES = {
        "sql": ["-w", "--with", "--append", "--interact"],
        "sqlplot": ["-w", "--with"],
        "sqlcmd": [],
    }

    DISALLOWED_ALIASES = {
        "sql": {
            "-l": "--connections",
            "-x": "--close",
            "-c": "--creator",
            "-s": "--section",
            "-p": "--persist",
            "-a": "--connection-arguments",
            "-f": "--file",
            "-n": "--no-index",
            "-S": "--save",
            "-A": "--alias",
        },
        "sqlplot": {
            "-t": "--table",
            "-s": "--schema",
            "-c": "--column",
            "-o": "--orient",
            "-b": "--bins",
            "-B": "--breaks",
            "-W": "--binwidth",
            "-S": "--show-numbers",
        },
        "sqlcmd": {
            "-t": "--table",
            "-s": "--schema",
            "-o": "--output",
        },
    }
    sql_line = ip.magics_manager.lsmagic()["line"][cmd_from]

    with pytest.raises(UsageError) as excinfo:
        magic_args(
            sql_line,
            line,
            cmd_from,
            ALLOWED_DUPLICATES[cmd_from],
            DISALLOWED_ALIASES[cmd_from],
        )
    assert expected_error_message in str(excinfo.value)


@pytest.mark.parametrize(
    "line, expected_out",
    [
        ("some-argument", {"line": ["some-argument"]}),
        ("a b c", {"line": ["a", "b", "c"]}),
        (
            "a b c --file query.sql",
            {"line": ["a", "b", "c"], "file": "query.sql"},
        ),
    ],
)
def test_magic_args(ip, line, expected_out):
    sql_line = ip.magics_manager.lsmagic()["line"]["sql"]

    args = magic_args(sql_line, line, "sql")
    assert args.__dict__ == complete_with_defaults(expected_out)


@pytest.mark.parametrize(
    "query, expected_escaped, expected_found",
    [
        ("SELECT * FROM table where x > :x", "SELECT * FROM table where x > :x", []),
        (
            "SELECT * FROM table where x > ':x'",
            "SELECT * FROM table where x > '\\:x'",
            ["x"],
        ),
        (
            'SELECT * FROM table where x > ":y"',
            'SELECT * FROM table where x > "\\:y"',
            ["y"],
        ),
        (
            "SELECT * FROM table where x > '':something''",
            "SELECT * FROM table where x > ''\\:something''",
            ["something"],
        ),
        (
            'SELECT * FROM table where x > "":var""',
            'SELECT * FROM table where x > ""\\:var""',
            ["var"],
        ),
    ],
    ids=[
        "no-escape",
        "single-quote",
        "double-quote",
        "double-single-quote",
        "double-double-quote",
    ],
)
def test_escape_string_literals_with_colon_prefix(
    query, expected_escaped, expected_found
):
    escaped, found = escape_string_literals_with_colon_prefix(query)
    assert escaped == expected_escaped
    assert found == expected_found


@pytest.mark.parametrize(
    "query, expected",
    [
        (
            "SELECT * FROM penguins WHERE species = :species AND mass = ':mass'",
            ["species"],
        ),
        (
            'SELECT * FROM penguins WHERE species = :species AND mass = ":mass"',
            ["species"],
        ),
        (
            "SELECT * FROM penguins WHERE species = :species AND mass = :mass",
            ["species", "mass"],
        ),
    ],
)
def test_find_named_parameters(query, expected):
    assert find_named_parameters(query) == expected


@pytest.mark.parametrize(
    "content, expected",
    [
        (
            """
[duck]
drivername = duckdb
""",
            None,
        ),
        (
            """
[default]
drivername = duckdb
""",
            "duckdb://",
        ),
        (
            """
[default]
drivername = postgresql
host = localhost
port = 5432
username = user
password = pass
database = db
""",
            "postgresql://user:pass@localhost:5432/db",
        ),
    ],
    ids=[
        "no-default",
        "default",
        "default-postgres",
    ],
)
def test_connections_file_get_default_connection_url(tmp_empty, content, expected):
    Path("conns.ini").write_text(content)

    cf = ConnectionsFile(path_to_file="conns.ini")
    assert cf.get_default_connection_url() == expected


@pytest.mark.parametrize(
    "query_jupysql, expected_duckdb",
    [
        (
            "select 'hello'[:2]",
            "he",
        ),
        (
            "select 'hello'[2:]",
            "ello",
        ),
        (
            "select 'hello'[2:4]",
            "ell",
        ),
        (
            "select 'hello'[:-1]",
            "hell",
        ),
    ],
)
def test_slicing_jupysql_matches_duckdb_expected(
    ip_empty, query_jupysql, expected_duckdb
):
    ip_empty.run_cell("%load_ext sql")
    ip_empty.run_cell("%sql duckdb://")
    raw_result = ip_empty.run_line_magic("sql", query_jupysql)
    result_jupysql = list(raw_result.dict().values())[0][0]
    assert result_jupysql == expected_duckdb


@pytest.mark.parametrize(
    "query, expected_escaped, expected_found",
    [
        (
            "SELECT 'hello'",
            "SELECT 'hello'",
            [],
        ),
        (
            "SELECT 'hello'[:]",
            "SELECT 'hello'[:]",
            [],
        ),
        (
            "SELECT 'hello'[:2]",
            "SELECT 'hello'[\\:2]",
            ["2"],
        ),
        (
            "SELECT 'hello'[1:5]",
            "SELECT 'hello'[1\\:5]",
            ["5"],
        ),
        (
            "SELECT 'hello'[1:99]",
            "SELECT 'hello'[1\\:99]",
            ["99"],
        ),
        (
            "SELECT 'hello'[:123456789]",
            "SELECT 'hello'[\\:123456789]",
            ["123456789"],
        ),
    ],
    ids=[
        "no-slicing",
        "slicing-empty",
        "end-index-only",
        "begin-end-index",
        "end-index-two-digit",
        "end-index-many-digit",
    ],
)
def test_escape_string_slicing_notation(query, expected_escaped, expected_found):
    escaped, found = escape_string_slicing_notation(query)
    assert escaped == expected_escaped
    assert found == expected_found


@pytest.mark.parametrize(
    "line, expected_args, expected_sql",
    [
        (
            "-p --save snippet -N",
            "-p --save snippet -N",
            "",
        ),
        (
            "select * from authors",
            "select * from authors",
            "",
        ),
        (
            "select '[1,2,3]'::json -> 1",
            "",
            "select '[1,2,3]'::json -> 1",
        ),
        (
            "--save snippet --alias query1 select '[1,2,3]'::json -> 1",
            "--save snippet --alias query1 ",
            "select '[1,2,3]'::json -> 1",
        ),
        (
            "--save snippet --alias query1 from authors select name \
where id = (readers ->> 0)",
            "--save snippet --alias query1 ",
            "from authors select name where id = (readers ->> 0)",
        ),
        (
            "--save snippet --alias query1 with temp as (select * from authors) \
select name where id = (publishers -> 'Scott')",
            "--save snippet --alias query1 ",
            "with temp as (select * from authors) select name \
where id = (publishers -> 'Scott')",
        ),
        (
            "--save snippet --alias query1 pivot authors on id \
where name = (names ->> 'Brenda')",
            "--save snippet --alias query1 ",
            "pivot authors on id where name = (names ->> 'Brenda')",
        ),
        (
            "-p --save snippet -N create table (names -> 1) (id INT, name VARCHAR(10))",
            "-p --save snippet -N ",
            "create table (names -> 1) (id INT, name VARCHAR(10))",
        ),
        (
            "-p --save snippet -N update authors where id = '[5,6]::json'->1",
            "-p --save snippet -N ",
            "update authors where id = '[5,6]::json'->1",
        ),
        (
            "-p --save snippet -N delete from authors where name = (books->>'Turner')",
            "-p --save snippet -N ",
            "delete from authors where name = (books->>'Turner')",
        ),
        (
            "-p --save snippet -N insert into authors values('[100]'::json->0)",
            "-p --save snippet -N ",
            "insert into authors values('[100]'::json->0)",
        ),
    ],
    ids=[
        "no-query",
        "no-args",
        "no-args-json",
        "select",
        "from",
        "with",
        "pivot",
        "create",
        "update",
        "delete",
        "insert",
    ],
)
def test_split_args_and_sql(line, expected_args, expected_sql):
    args_line, sql_line = split_args_and_sql(line)
    assert args_line == expected_args
    assert sql_line == expected_sql
