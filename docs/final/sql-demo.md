# SQL demo guide

Run [sql-demo.sql](sql-demo.sql) against a read-only PostgreSQL connection after `alembic upgrade
head`. The file contains 20 non-mutating examples covering JOIN, LEFT JOIN, GROUP BY, filtered
aggregates, correlated subquery, CTE and `row_number`/`dense_rank` window functions. Show queries 2,
7, 11, 16 and 17 during a short defense; counts are live and must not be copied from old reports.
