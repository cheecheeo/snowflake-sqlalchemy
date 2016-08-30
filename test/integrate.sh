# shellcheck disable=1091
source /tmp/test_snowflake_sqlalchemy/bin/activate &&
pip install pytest numpy pandas &&
pip install dist/snowflake_sqlalchemy*.whl &&
cat > test/parameters.py << EOF
CONNECTION_PARAMETERS = {
  'account':  '$ACCOUNT',
  'user':     '$USER',
  'password': '$PASSWORD',
  'schema':   '$SCHEMA',
  'database': 'testdb',
}
EOF
py.test test
