"""Ensure SQLite savepoints participate in the outer transaction."""
from sqlalchemy import event


def configure_sqlite_transactions(engine):
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def configure_connection(dbapi_connection, connection_record):
        # SQLAlchemy controls BEGIN instead of sqlite3's legacy behavior.
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def begin_transaction(connection):
        connection.exec_driver_sql("BEGIN")
