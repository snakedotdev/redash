import logging
import duckdb
from redash.query_runner import BaseSQLQueryRunner, register, JobTimeoutException
from redash.utils import json_dumps, json_loads

logger = logging.getLogger(__name__)

class Duckdb(BaseSQLQueryRunner):
    noop_query = "PRAGMA show_tables"

    @classmethod
    def configuration_schema(cls):
        return {
            "type": "object",
            "properties": {"dbpath": {"type": "string", "title": "Database Path"}},
            "required": ["dbpath"],
        }

    @classmethod
    def type(cls):
        return "duckdb"

    def __init__(self, configuration):
        super(Duckdb, self).__init__(configuration)
        self._dbpath = self.configuration["dbpath"]

    def _get_tables(self, schema):
        logger.info("Called _get_tables: %r", schema)

        # XXX this doesn't work for views
        query_table = "SHOW ALL TABLES"
        query_columns = """PRAGMA table_info('%s')"""

        results, error = self.run_query(query_table, None)

        if error is not None:
            raise Exception("Failed getting schema.")

        results = json_loads(results)

        for row in results["rows"]:
            table_name = row["name"]
            schema[table_name] = {"name": table_name, "columns": []}
            results_table, error = self.run_query(query_columns % (table_name,), None)
            if error is not None:
                self._handle_run_query_error(error)

            results_table = json_loads(results_table)
            for row_column in results_table["rows"]:
                d = {"name": row_column["name"], "type": row_column["type"]}
                schema[table_name]["columns"].append(d)

        logger.info("Introspected schema: %r", list(schema.values()))

        return list(schema.values())

    def run_query(self, query, user):
        dbpath = self.configuration.get('dbpath',None)
        logger.info("Connecting to %s", dbpath)
        connection = duckdb.connect(dbpath, read_only=True)
        cursor = connection.cursor()
        logger.info("Connected to %s", dbpath)
        try:
            logger.info("Running %r", query)
            cursor.execute(query)
            logger.info("Ran %r", query)

            if cursor.description is not None:
                columns = self.fetch_columns([(i[0], None) for i in cursor.description])
                rows = [
                    dict(zip((column["name"] for column in columns), row))
                    for row in cursor.fetchall()
                ]

                data = {"columns": columns, "rows": rows}
                error = None

                json_data = json_dumps(data)

            else:
                error = "Query completed but it returned no data."
                json_data = None
        except (KeyboardInterrupt, JobTimeoutException):
            connection.cancel()
            raise
        finally:
            connection.close()

        if error:
            logger.info("Query had error: %r", error)
        return json_data, error


register(Duckdb)
